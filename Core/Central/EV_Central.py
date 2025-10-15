"""
Módulo que representa la central de control de toda la solución. Implementa la lógica y gobierno de todo el sistema.
"""

import sys
import os
import time
import uuid
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.SqliteConnection import SqliteConnection
from Common.MessageFormatter import MessageFormatter
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager
from Common.MySocketServer import MySocketServer
from Common.Status import Status


class EV_Central:
    def __init__(self, logger=None):
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()

        self.logger = logger
        self.socket_server = None
        self.db_manager = None  # 这个用来存储数据库管理对象
        self.db_path = self.config.get_db_path()
        self.sql_schema = os.path.join("Core", "BD", "table.sql")
        self.running = False

        if not self.debug_mode:
            self.tools = AppArgumentParser(
                app_name="EV_Central",
                description="Sistema Central de Control para Puntos de Recarga de Vehículos Eléctricos",
            )
            self.tools.add_argument("listen_port", type=int, help="Puerto de escuha")
            self.tools.add_argument(
                "broker",
                type=ip_port_type,
                help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)",
            )
            self.tools.add_argument(
                "--db",
                type=ip_port_type,
                help="IP y puerto del servidor de base de datos (formato IP:PORT)",
                default=("localhost", 5432),
            )
            self.args = self.tools.parse_args()

        else:

            class Args:
                listen_port = self.config.get_listen_port()
                broker = self.config.get_broker()
                db = self.config.get_db()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

    def _init_database(self):
        self.logger.debug("Initializing database connection")
        try:
            # 连接到 SQLite 数据库
            # 对这个属性进行操作，而不是直接使用 SqliteConnection 类
            self.db_manager = SqliteConnection(
                db_path=self.db_path,
                sql_schema_file=self.sql_schema,
                create_tables_if_not_exist=True,
            )
            if not self.db_manager.is_sqlite_available():
                self.logger.error(
                    "Database is not available or not properly initialized."
                )
                sys.exit(1)

            self.db_manager.set_all_charging_points_status(Status.DISCONNECTED.value)
            charging_points_count = len(self.db_manager.get_all_charging_points())
            self.logger.info(
                f"Database initialized successfully. {charging_points_count} charging points set to DISCONNECTED."
            )

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)

    def _init_socket_server(self):
        """
        Initialize the socket server to listen for incoming connections from charging points.
        """
        self.logger.debug("Initializing socket server")
        self._cp_connections = {}  # {cp_id: client_socket}
        self._client_to_cp = {}  # {client_id: cp_id}
        try:

            # 将自定义消息处理函数分配给 socket 服务器
            self.socket_server = MySocketServer(
                host=self.config.get_ip_port_ev_cp_central()[0],
                port=self.config.get_ip_port_ev_cp_central()[1],
                logger=self.logger,
                message_callback=self._process_charging_point_message,
                disconnect_callback=self._handle_client_disconnect,
            )
            # 通过MySocketServer类的start方法启动服务器
            self.socket_server.start()
            self.running = True
            self.logger.debug("Socket server initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize socket server: {e}")
            sys.exit(1)

    def _handle_client_disconnect(self, client_id):
        """处理客户端断开连接"""
        if client_id in self._client_to_cp:
            cp_id = self._client_to_cp[client_id]
            self.logger.info(f"Client {client_id} (CP: {cp_id}) disconnected")

            # 更新数据库状态为离线
            try:
                self.db_manager.update_charging_point_status(
                    cp_id=cp_id,
                    status=Status.DISCONNECTED.value,
                )
                self.logger.info(f"Charging point {cp_id} set to DISCONNECTED.")
            except Exception as e:
                self.logger.error(f"Failed to update status for {cp_id}: {e}")

            # 清理映射关系
            del self._cp_connections[cp_id]
            del self._client_to_cp[client_id]

    def _process_charging_point_message(self, client_id, message):
        """
        作为消息的分发中心。根据消息的 'type' 字段，调用相应的处理方法。
        """
        self.logger.info(f"收到来自客户端 {client_id} 的消息: {message}")

        msg_type = message.get("type")

        handlers = {
            "register_request": self._handle_register_message,
            "heartbeat_request": self._handle_heartbeat_message,
            "charge_request": self._handle_charge_request_message,
            "charging_data": self._handle_charging_data_message,
            "charge_completion": self._handle_charge_completion_message,
            "fault_notification": self._handle_fault_notification_message,
            "status_update": self._handle_status_update_message,
            "available_cps_request": self._handle_available_cps_request,
        }

        handler = handlers.get(msg_type)
        if handler:
            return handler(client_id, message)
        else:
            self.logger.error(f"Unknown message type from {client_id}: '{msg_type}'")
            return MessageFormatter.create_response_message(
                cp_type=f"{msg_type}_response",
                message_id=message.get("message_id", ""),
                status="failure",
                info=f"Unknown message type: '{msg_type}'",
            )

    def _handle_register_message(self, client_id, message):  # TODO: review
        """
        专门处理充电桩的注册请求。
        """
        self.logger.info(f"正在处理来自 {client_id} 的注册请求...")

        cp_id = message.get("id")
        location = message.get("location")
        price_per_kwh = message.get("price_per_kwh")
        message_id = message.get("message_id")

        if not message_id:
            return MessageFormatter.create_response_message(
                cp_type="register_response",
                message_id="",
                status="failure",
                info="注册消息中缺少 message_id 字段",
            )

        missing_fields = []
        if not cp_id:
            missing_fields.append("id")
        if not location:
            missing_fields.append("location")
        if price_per_kwh is None:
            missing_fields.append("price_per_kwh")
        if missing_fields:
            return MessageFormatter.create_response_message(
                cp_type="register_response",
                message_id=message_id,
                status="failure",
                info=f"注册消息中缺少字段: {', '.join(missing_fields)}",
            )

        # 插入数据库
        try:
            price_per_kwh = float(price_per_kwh)
            if price_per_kwh < 0:
                raise ValueError("price_per_kwh must be non-negative")

            self.logger.debug(f"尝试将充电桩 {cp_id} 注册到数据库...")
            self.db_manager.insert_or_update_charging_point(
                cp_id=cp_id,
                location=location,
                price_per_kwh=price_per_kwh,
                status=Status.DISCONNECTED.value,  # 初始状态为 DISCONNECTED，等待心跳消息更新
                last_connection_time=None,
            )
            self.logger.info(f"充电桩 {cp_id} 注册成功！")
        except Exception as e:
            self.logger.debug(f"注册充电桩 {cp_id} 失败: {e}")
            return MessageFormatter.create_response_message(
                cp_type="register_response",
                message_id=message_id,
                status="failure",
                info=f"注册失败: {e}",
            )

        # 维护连接映射
        self._cp_connections[cp_id] = client_id
        self._client_to_cp[client_id] = cp_id

        self._show_registered_charging_points()

        return MessageFormatter.create_response_message(
            cp_type="register_response",
            message_id=message.get("message_id", ""),
            status="success",
            info=f"charging point {cp_id} registered successfully.",
        )

    def _handle_charge_request_message(self, client_id, message):
        """
        处理来自司机应用程序或充电点本身的充电请求。
        需要验证充电点是否可用，并决定是否授权。
        成功授权后，需要向充电点和司机应用程序发送授权通知。
        """
        self.logger.info(f"正在处理来自 {client_id} 的充电请求...")
        
        cp_id = message.get("cp_id")
        driver_id = message.get("driver_id")
        message_id = message.get("message_id")
        
        if not cp_id or not driver_id or not message_id:
            return MessageFormatter.create_response_message(
                cp_type="charge_request_response",
                message_id=message_id or "",
                status="failure",
                info="充电请求消息中缺少必要字段: cp_id, driver_id, message_id",
            )
        
        # 检查充电点是否已注册且可用
        if not self.db_manager.is_charging_point_registered(cp_id):
            return MessageFormatter.create_response_message(
                cp_type="charge_request_response",
                message_id=message_id,
                status="failure",
                info=f"充电点 {cp_id} 未注册",
            )
        
        # 获取充电点状态
        charging_points = self.db_manager.get_all_charging_points()
        cp_status = None
        for cp in charging_points:
            if cp["id"] == cp_id:
                cp_status = cp["status"]
                break
        
        if cp_status != "ACTIVE":
            return MessageFormatter.create_response_message(
                cp_type="charge_request_response",
                message_id=message_id,
                status="failure",
                info=f"充电点 {cp_id} 当前状态为 {cp_status}，无法进行充电",
            )
        
        # 授权充电请求
        self.logger.info(f"授权充电请求: CP {cp_id}, Driver {driver_id}")
        
        try:
            # 生成充电会话ID
            import uuid
            session_id = str(uuid.uuid4())
            
            # 注册司机（如果尚未注册）
            self.db_manager.register_driver(driver_id, f"driver_{driver_id}")
            
            # 创建充电会话
            from datetime import datetime
            start_time = datetime.now().isoformat()
            
            if not self.db_manager.create_charging_session(session_id, cp_id, driver_id, start_time):
                raise Exception("创建充电会话失败")
            
            # 更新充电点状态为充电中
            self.db_manager.update_charging_point_status(
                cp_id=cp_id,
                status="CHARGING"
            )
            
            # 向Monitor发送启动充电命令
            self._send_start_charging_to_monitor(cp_id, session_id, driver_id)
            
            return MessageFormatter.create_response_message(
                cp_type="charge_request_response",
                message_id=message_id,
                status="success",
                info=f"充电请求已授权，充电点 {cp_id} 开始为司机 {driver_id} 充电，会话ID: {session_id}",
                session_id=session_id
            )
        except Exception as e:
            self.logger.error(f"授权充电请求失败: {e}")
            return MessageFormatter.create_response_message(
                cp_type="charge_request_response",
                message_id=message_id,
                status="failure",
                info=f"授权失败: {e}",
            )

    def _handle_charge_completion_message(self, client_id, message):
        """
        处理充电完成的通知。
        需要更新充电点和车辆的状态，并记录充电会话的详细信息。
        """
        self.logger.info(f"正在处理来自 {client_id} 的充电完成通知...")
        
        cp_id = message.get("cp_id")
        driver_id = message.get("driver_id")
        energy_consumed = message.get("energy_consumed_kwh")
        total_cost = message.get("total_cost")
        message_id = message.get("message_id")
        
        if not cp_id or not message_id:
            return MessageFormatter.create_response_message(
                cp_type="charge_completion_response",
                message_id=message_id or "",
                status="failure",
                info="充电完成消息中缺少必要字段: cp_id, message_id",
            )
        
        try:
            # 获取会话ID
            session_id = message.get("session_id")
            if not session_id:
                return MessageFormatter.create_response_message(
                    cp_type="charge_completion_response",
                    message_id=message_id,
                    status="failure",
                    info="充电完成消息中缺少会话ID",
                )
            
            # 更新充电会话
            from datetime import datetime
            end_time = datetime.now().isoformat()
            
            self.db_manager.update_charging_session(
                session_id=session_id,
                end_time=end_time,
                energy_consumed=energy_consumed,
                total_cost=total_cost,
                status="completed"
            )
            
            # 更新充电点状态为活跃
            self.db_manager.update_charging_point_status(
                cp_id=cp_id,
                status="ACTIVE"
            )
            
            self.logger.info(f"充电完成: CP {cp_id}, 会话 {session_id}, 消耗电量: {energy_consumed}kWh, 费用: €{total_cost}")
            
            return MessageFormatter.create_response_message(
                cp_type="charge_completion_response",
                message_id=message_id,
                status="success",
                info=f"充电完成通知已处理，充电点 {cp_id} 状态已更新为活跃",
            )
        except Exception as e:
            self.logger.error(f"处理充电完成通知失败: {e}")
            return MessageFormatter.create_response_message(
                cp_type="charge_completion_response",
                message_id=message_id,
                status="failure",
                info=f"处理失败: {e}",
            )

    def _handle_status_update_message(self, client_id, message):
        """
        处理充电点发送的状态更新消息。
        需要更新其在数据库中的状态，并可能触发其他操作（如通知管理员）。
        """
        self.logger.info(f"正在处理来自 {client_id} 的状态更新...")
        
        cp_id = message.get("id")
        new_status = message.get("status")
        message_id = message.get("message_id")
        
        if not cp_id or not new_status or not message_id:
            return MessageFormatter.create_response_message(
                cp_type="status_update_response",
                message_id=message_id or "",
                status="failure",
                info="状态更新消息中缺少必要字段: id, status, message_id",
            )
        
        # 验证状态值是否有效
        valid_statuses = ["ACTIVE", "STOPPED", "CHARGING", "FAULTY", "DISCONNECTED"]
        if new_status not in valid_statuses:
            return MessageFormatter.create_response_message(
                cp_type="status_update_response",
                message_id=message_id,
                status="failure",
                info=f"无效的状态值: {new_status}。有效状态: {', '.join(valid_statuses)}",
            )
        
        try:
            # 更新数据库中的状态
            self.db_manager.update_charging_point_status(
                cp_id=cp_id,
                status=new_status
            )
            
            self.logger.info(f"充电点 {cp_id} 状态已更新为: {new_status}")
            
            # 如果状态为故障，记录故障信息
            if new_status == "FAULTY":
                self.logger.warning(f"充电点 {cp_id} 报告故障状态")
                # TODO: 可以在这里添加通知管理员的逻辑
            
            return MessageFormatter.create_response_message(
                cp_type="status_update_response",
                message_id=message_id,
                status="success",
                info=f"充电点 {cp_id} 状态已更新为 {new_status}",
            )
        except Exception as e:
            self.logger.error(f"更新充电点状态失败: {e}")
            return MessageFormatter.create_response_message(
                cp_type="status_update_response",
                message_id=message_id,
                status="failure",
                info=f"状态更新失败: {e}",
            )

    def _handle_authorization_message(
        self, cp_id, client_id, message
    ):  # TODO: implement
        """
        处理来自司机应用程序或充电点本身的充电授权请求。
        需要验证充电点是否可用，并决定是否授权。
        成功授权后，需要向充电点和司机应用程序发送授权通知。
        """
        pass

    def _handle_charging_data_message(self, client_id, message):
        """
        处理充电点在充电过程中实时发送的电量消耗和费用信息。
        这些数据需要更新到内部状态和数据库，并显示在监控面板上。
        """
        self.logger.info(f"正在处理来自 {client_id} 的充电数据...")
        
        session_id = message.get("session_id")
        energy_consumed = message.get("energy_consumed_kwh")
        total_cost = message.get("total_cost")
        charging_rate = message.get("charging_rate")
        message_id = message.get("message_id")
        
        if not session_id or not message_id:
            return MessageFormatter.create_response_message(
                cp_type="charging_data_response",
                message_id=message_id or "",
                status="failure",
                info="充电数据消息中缺少必要字段: session_id, message_id",
            )
        
        try:
            # 更新数据库中的充电会话
            self.db_manager.update_charging_session(
                session_id=session_id,
                energy_consumed=energy_consumed,
                total_cost=total_cost,
                status="in_progress"
            )
            
            # 获取充电会话信息
            session_info = self.db_manager.get_charging_session(session_id)
            if session_info:
                cp_id = session_info["cp_id"]
                driver_id = session_info["driver_id"]
                
                # 发送充电状态更新给Driver
                self._send_charging_status_to_driver(driver_id, {
                    "session_id": session_id,
                    "energy_consumed_kwh": energy_consumed,
                    "total_cost": total_cost,
                    "charging_rate": charging_rate,
                    "timestamp": int(time.time())
                })
                
                self.logger.info(f"充电数据更新: 会话 {session_id}, 电量: {energy_consumed}kWh, 费用: €{total_cost}")
            
            return MessageFormatter.create_response_message(
                cp_type="charging_data_response",
                message_id=message_id,
                status="success",
                info="充电数据已处理",
            )
        except Exception as e:
            self.logger.error(f"处理充电数据失败: {e}")
            return MessageFormatter.create_response_message(
                cp_type="charging_data_response",
                message_id=message_id,
                status="failure",
                info=f"处理失败: {e}",
            )

    def _handle_fault_notification_message(self, client_id, message):
        """
        处理充电点发送的故障或异常通知。
        需要记录这些事件，并可能触发警报或通知维护人员。
        """
        self.logger.warning(f"收到来自 {client_id} 的故障通知...")
        
        cp_id = message.get("id")
        failure_info = message.get("failure_info")
        message_id = message.get("message_id")
        
        if not cp_id or not failure_info or not message_id:
            return MessageFormatter.create_response_message(
                cp_type="fault_notification_response",
                message_id=message_id or "",
                status="failure",
                info="故障通知消息中缺少必要字段: id, failure_info, message_id",
            )
        
        try:
            # 更新充电点状态为故障
            self.db_manager.update_charging_point_status(
                cp_id=cp_id,
                status="FAULTY"
            )
            
            self.logger.error(f"充电点 {cp_id} 故障: {failure_info}")
            
            # TODO: 在这里可以添加通知维护人员的逻辑
            # 例如：发送邮件、短信或推送到监控系统
            
            return MessageFormatter.create_response_message(
                cp_type="fault_notification_response",
                message_id=message_id,
                status="success",
                info=f"故障通知已记录，充电点 {cp_id} 状态已更新为故障",
            )
        except Exception as e:
            self.logger.error(f"处理故障通知失败: {e}")
            return MessageFormatter.create_response_message(
                cp_type="fault_notification_response",
                message_id=message_id,
                status="failure",
                info=f"故障通知处理失败: {e}",
            )

    def _handle_recovery_message(self, client_id, message):
        """
        处理充电点在故障修复后发送的恢复通知。
        需要更新其状态，并可能重新启用其服务。
        """
        self.logger.info(f"收到来自 {client_id} 的恢复通知...")
        
        cp_id = message.get("id")
        recovery_info = message.get("recovery_info", "故障已修复")
        message_id = message.get("message_id")
        
        if not cp_id or not message_id:
            return MessageFormatter.create_response_message(
                cp_type="recovery_response",
                message_id=message_id or "",
                status="failure",
                info="恢复通知消息中缺少必要字段: id, message_id",
            )
        
        try:
            # 更新充电点状态为活跃
            self.db_manager.update_charging_point_status(
                cp_id=cp_id,
                status="ACTIVE"
            )
            
            self.logger.info(f"充电点 {cp_id} 已恢复: {recovery_info}")
            
            return MessageFormatter.create_response_message(
                cp_type="recovery_response",
                message_id=message_id,
                status="success",
                info=f"恢复通知已处理，充电点 {cp_id} 状态已更新为活跃",
            )
        except Exception as e:
            self.logger.error(f"处理恢复通知失败: {e}")
            return MessageFormatter.create_response_message(
                cp_type="recovery_response",
                message_id=message_id,
                status="failure",
                info=f"恢复通知处理失败: {e}",
            )

    def _handle_available_cps_request(self, client_id, message):
        """处理可用充电点请求"""
        self.logger.info(f"收到来自 {client_id} 的可用充电点请求...")
        
        message_id = message.get("message_id")
        driver_id = message.get("driver_id")
        
        try:
            # 获取所有充电点
            charging_points = self.get_all_registered_charging_points()
            
            # 过滤可用充电点（状态为ACTIVE的）
            available_cps = [
                {
                    "id": cp["id"],
                    "location": cp["location"],
                    "price_per_kwh": cp["price_per_kwh"],
                    "status": cp["status"]
                }
                for cp in charging_points
                if cp["status"] == "ACTIVE"
            ]
            
            self.logger.info(f"Found {len(available_cps)} available charging points")
            
            return {
                "type": "available_cps_response",
                "message_id": message_id,
                "status": "success",
                "driver_id": driver_id,
                "charging_points": available_cps,
                "timestamp": int(time.time())
            }
            
        except Exception as e:
            self.logger.error(f"处理可用充电点请求失败: {e}")
            return {
                "type": "available_cps_response",
                "message_id": message_id,
                "status": "failure",
                "driver_id": driver_id,
                "error": str(e),
                "timestamp": int(time.time())
            }

    def _handle_heartbeat_message(self, client_id, message):
        """
        处理充电桩发送的心跳消息，更新其最后连接时间。
        这个函数是用来检测充电桩是否在线的。要求每30秒发送一次心跳消息。
        """
        self.logger.info(f"Processing heartbeat from client {client_id}")
        cp_id = message.get("id")

        if not cp_id:
            return MessageFormatter.create_response_message(
                cp_type="heartbeat_response",
                message_id=message.get("message_id", ""),
                status="failure",
                info="心跳消息中缺少 id 字段",
            )

        # 检查充电桩是否已注册
        if self.db_manager.is_charging_point_registered(cp_id):
            current_time = datetime.now(timezone.utc).isoformat()
            try:
                # 直接更新状态和最后连接时间
                self.db_manager.update_charging_point_status(
                    cp_id=cp_id,
                    status=Status.ACTIVE.value,
                    last_connection_time=current_time,
                )

                # 更新连接映射
                self._cp_connections[cp_id] = client_id
                self._client_to_cp[client_id] = cp_id

                self.logger.info(f"Heartbeat from {cp_id} processed successfully")
                self._show_registered_charging_points()

                return MessageFormatter.create_response_message(
                    cp_type="heartbeat_response",
                    message_id=message.get("message_id", ""),
                    status="success",
                    info="Heartbeat received and last connection time updated.",
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to update last connection time for {cp_id}: {e}"
                )
                return MessageFormatter.create_response_message(
                    cp_type="heartbeat_response",
                    message_id=message.get("message_id", ""),
                    status="failure",
                    info=f"Failed to update last connection time: {e}",
                )
        else:
            self.logger.warning(
                f"Received heartbeat from unregistered charging point {cp_id}"
            )
            return MessageFormatter.create_response_message(
                cp_type="heartbeat_response",
                message_id=message.get("message_id", ""),
                status="failure",
                info=f"Charging point {cp_id} is not registered.",
            )

    def _send_message_to_client(self, client_id, message):
        """
        向指定客户端发送消息
        """
        try:
            if self.socket_server:
                self.socket_server.send_message_to_client(client_id, message)
                self.logger.debug(f"消息已发送给客户端 {client_id}: {message}")
            else:
                self.logger.error("Socket服务器未初始化")
        except Exception as e:
            self.logger.error(f"向客户端 {client_id} 发送消息失败: {e}")

    def _send_charging_status_to_driver(self, driver_id, charging_data):
        """
        向指定司机发送充电状态更新
        """
        self.logger.debug(f"向司机 {driver_id} 发送充电状态更新: {charging_data}")
        self.logger.warning("此功能尚未实现，需要通过消息队列或其他方式发送给司机应用程序")

    def _send_start_charging_to_monitor(self, cp_id, session_id, driver_id):
        """
        向Monitor发送启动充电命令
        """
        try:
            # 查找连接到该充电点的Monitor客户端
            monitor_client_id = self._cp_connections.get(cp_id)
            if not monitor_client_id:
                self.logger.error(f"未找到充电点 {cp_id} 的Monitor连接")
                return False
            
            # 构建启动充电命令
            start_charging_message = {
                "type": "start_charging_command",
                "message_id": str(uuid.uuid4()),
                "cp_id": cp_id,
                "session_id": session_id,
                "driver_id": driver_id,
                "timestamp": int(time.time())
            }
            
            # 发送给Monitor
            self._send_message_to_client(monitor_client_id, start_charging_message)
            self.logger.info(f"启动充电命令已发送给Monitor: CP {cp_id}, 会话 {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"发送启动充电命令失败: {e}")
            return False

    def _handle_manual_command(self, cp_id, command):  # TODO: implement
        """
        处理来自管理员的手动命令，如启动或停止充电点。
        这些命令需要通过消息队列发送到相应的充电点。
        """
        pass

    def _generate_unique_message_id(self):
        """
        生成一个唯一的消息ID，使用UUID
        """
        import uuid

        return str(uuid.uuid4())

    def _show_registered_charging_points(self):
        """
        打印所有已注册的充电桩及其状态。
        """
        charging_points = self.get_all_registered_charging_points()
        if not charging_points:
            print("No registered charging points found.")
            return

        print("\n" + "╔" + "═" * 60 + "╗")
        print("║" + " Puntos de recarga registrados ".center(60) + "║")
        print("╚" + "═" * 60 + "╝\n")

        for i, cp in enumerate(charging_points, 1):
            print(f"【{i}】 charging point {cp['id']}")
            print(f"    ├─ Location: {cp['location']}")
            print(f"    ├─ Price/kWh: €{cp['price_per_kwh']}/kWh")
            print(f"    ├─ Status: {cp['status']}")
            print(f"    └─ Last Connection: {cp['last_connection_time']}")
            print()

    def get_all_registered_charging_points(self):
        """
        Retrieve all registered charging points from the database.
        Returns a list of dictionaries with charging point details.
        """
        if not self.db_manager:
            self.logger.error("Database connection is not initialized.")
            return []

        return self.db_manager.get_all_charging_points()

    def _init_kafka_producer(self):  # TODO: implement
        self.logger.debug("Initializing Kafka producer")
        pass

    def _init_kafka_consumer(self):  # TODO: implement
        self.logger.debug("Initializing Kafka consumer")
        pass

    def initialize_systems(self):
        self.logger.info("Initializing systems...")
        self._init_database()
        self._init_socket_server()

        # self._init_kafka_producer()
        # self._init_kafka_consumer()
        self.logger.info("All systems initialized successfully.")
        self._show_registered_charging_points()

    def shutdown_systems(self):
        self.logger.info("Shutting down systems...")
        if self.socket_server:
            self.socket_server.stop()
        if self.db_manager:
            try:
                self.db_manager.set_all_charging_points_status(
                    Status.DISCONNECTED.value
                )
                self.logger.info("All charging points set to DISCONNECTED.")
            except Exception as e:
                self.logger.error(f"Error setting charging points to DISCONNECTED: {e}")
        self.running = False

    def start(self):
        self.logger.debug(f"Starting EV Central on port {self.args.listen_port}")
        self.logger.debug(
            f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )
        self.logger.debug(
            f"Connecting to Database at {self.args.db[0]}:{self.args.db[1]}"
        )

        self.initialize_systems()
        try:
            ## SOCKET HERE ##
            while self.running:
                import time

                time.sleep(1)
                pass  # TODO 这里在部署的时候不能用死循环，需要改成非阻塞的方式
        except KeyboardInterrupt:
            self.logger.info("Shutting down EV Central")
            self.shutdown_systems()
            sys.exit(0)


if __name__ == "__main__":

    logger = CustomLogger.get_logger()
    ev_central = EV_Central(logger=logger)
    ev_central.start()

# TODO 解决如果用户发送少了属性服务器也要返回相对的错误信息给用户
