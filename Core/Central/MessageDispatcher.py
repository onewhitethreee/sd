"""
你的 _process_charging_point_message 逻辑非常好，这是这个类中少有的亮点。把它提取出来，作为一个独立的 MessageDispatcher 类。
EV_Central 的 _process_charging_point_message 只需要把消息转发给这个 MessageDispatcher。
MessageDispatcher 内部维护 handlers 字典。
"""

import os
import sys
from datetime import datetime, timezone
import time
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.SqliteConnection import SqliteConnection
from Common.MessageFormatter import MessageFormatter
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager
from Common.MySocketServer import MySocketServer
from Common.Status import Status


class MessageDispatcher:
    def __init__(
        self,
        logger: CustomLogger,
        db_manager: SqliteConnection,
        socket_server,
        charging_points_connections,
        client_to_ref,
    ):
        self.logger = logger
        self.db_manager = db_manager
        self.socket_server = socket_server
        self._cp_connections = charging_points_connections
        self._client_to_cp = client_to_ref
        self.handlers = {
            "register_request": self._handle_register_message,
            "heartbeat_request": self._handle_heartbeat_message,
            "charge_request": self._handle_charge_request_message,
            "charging_data": self._handle_charging_data_message,
            "charge_completion": self._handle_charge_completion_message,
            "fault_notification": self._handle_fault_notification_message,
            "status_update": self._handle_status_update_message,
            "available_cps_request": self._handle_available_cps_request,
            "recovery_notification": self._handle_recovery_message,
            # "authorization_request": self._handle_authorization_message,  # TODO: implement
        }

    def dispatch_message(self, client_id, message):
        
        handler = self.handlers.get(message.get("type"))
        if not handler:
            return {
                "type": "error_response",
                "message_id": message.get("message_id", ""),
                "status": "failure",
                "info": f"未知消息类型: {message.get('type')}",
            }
        return handler(client_id, message)
    
    def _create_failure_response(self, message_type: str, message_id, info: str) -> dict:
        return MessageFormatter.create_response_message(
            cp_type=f"{message_type}_response",
            message_id=message_id,
            status="failure",
            info=info,
        )
    def _check_missing_fields(self, message: dict, required_fields: list):
        missing = [field for field in required_fields if message.get(field) is None]
        if missing:
            return f"消息中缺少必要字段: {', '.join(missing)}"
        return None

    def _handle_register_message(self, client_id, message):
        """
        专门处理充电桩的注册请求。
        """
        self.logger.info(f"正在处理来自 {client_id} 的注册请求...")

        cp_id = message.get("id")
        location = message.get("location")
        price_per_kwh = message.get("price_per_kwh")
        message_id = message.get("message_id")

        if message_id is None:
            return self._create_failure_response(
                "register",
                message_id="",
                info="注册消息中缺少 message_id 字段",
            )
        missing_info = self._check_missing_fields(
            message, ["id", "location", "price_per_kwh", "message_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "register",
                message_id=message_id,
                info=missing_info,
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

    def _handle_heartbeat_message(self, client_id, message):
        """
        处理充电桩发送的心跳消息，更新其最后连接时间。
        这个函数是用来检测充电桩是否在线的。要求每30秒发送一次心跳消息。
        """
        self.logger.info(f"Processing heartbeat from client {client_id}")
        cp_id = message.get("id")

        if not cp_id:
            return self._create_failure_response(
                "heartbeat",
                message_id=message.get("message_id", ""),
                info="Heartbeat message missing 'id' field",
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
                return self._create_failure_response(
                    "heartbeat",
                    message_id=message.get("message_id", ""),
                    info=f"Failed to update last connection time: {e}",
                )
        else:
            self.logger.warning(
                f"Received heartbeat from unregistered charging point {cp_id}"
            )
            return self._create_failure_response(
                "heartbeat",
                message_id=message.get("message_id", ""),
                info=f"Charging point {cp_id} is not registered.",
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
        
        missing_info = self._check_missing_fields(
            message, ["cp_id", "driver_id", "message_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "charge_request",
                message_id=message_id or "",
                info=missing_info,
            )

        # 检查充电点是否已注册且可用
        if not self.db_manager.is_charging_point_registered(cp_id):
            return MessageFormatter.create_response_message(
                cp_type="charge_request_response",
                message_id=message_id,
                status="failure",
                info=f"充电点 {cp_id} 未注册",
            )

        cp_status = self.db_manager.get_charging_point_status(cp_id)

        if cp_status != Status.ACTIVE.value:
            return self._create_failure_response(
                "charge_request",
                message_id=message_id,
                info=f"充电点 {cp_id} 当前状态为 {cp_status}，无法进行充电",
            )

        # 授权充电请求
        self.logger.info(f"授权充电请求: CP {cp_id}, Driver {driver_id}")

        try:
            # 生成充电会话ID

            session_id = str(uuid.uuid4())

            # 注册司机（如果尚未注册）
            self.db_manager.register_driver(driver_id, f"driver_{driver_id}")

            start_time = datetime.now().isoformat()

            if not self.db_manager.create_charging_session(
                session_id, cp_id, driver_id, start_time
            ):
                raise Exception("创建充电会话失败")

            # 更新充电点状态为充电中
            self.db_manager.update_charging_point_status(cp_id=cp_id, status=Status.CHARGING.value)

            # 向Monitor发送启动充电命令
            self._send_start_charging_to_monitor(cp_id, session_id, driver_id)

            return MessageFormatter.create_response_message(
                cp_type="charge_request_response",
                message_id=message_id,
                status="success",
                info=f"充电请求已授权，充电点 {cp_id} 开始为司机 {driver_id} 充电，会话ID: {session_id}",
                session_id=session_id,
            )
        except Exception as e:
            self.logger.error(f"授权充电请求失败: {e}")
            return self._create_failure_response(
                "charge_request",
                message_id=message_id,
                info=f"授权失败: {e}",
            )

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

        missing_info = self._check_missing_fields(
            message, ["session_id", "energy_consumed_kwh", "total_cost", "charging_rate", "message_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "charging_data",
                message_id=message_id or "",
                info=missing_info,
            )

        try:
            # 更新数据库中的充电会话
            self.db_manager.update_charging_session(
                session_id=session_id,
                energy_consumed=energy_consumed,
                total_cost=total_cost,
                status="in_progress",
            )

            # 获取充电会话信息
            session_info = self.db_manager.get_charging_session(session_id)
            if session_info:
                cp_id = session_info["cp_id"]
                driver_id = session_info["driver_id"]

                # 发送充电状态更新给Driver
                self._send_charging_status_to_driver(
                    driver_id,
                    {
                        "session_id": session_id,
                        "energy_consumed_kwh": energy_consumed,
                        "total_cost": total_cost,
                        "charging_rate": charging_rate,
                        "timestamp": int(time.time()),
                    },
                )

                self.logger.info(
                    f"充电数据更新: 会话 {session_id}, 电量: {energy_consumed}kWh, 费用: €{total_cost}"
                )

            return MessageFormatter.create_response_message(
                cp_type="charging_data_response",
                message_id=message_id,
                status="success",
                info="充电数据已处理",
            )
        except Exception as e:
            self.logger.error(f"处理充电数据失败: {e}")
            return self._create_failure_response(
                "charging_data",
                message_id=message_id,
                info=f"处理失败: {e}",
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

        missing_info = self._check_missing_fields(
            message, ["cp_id", "driver_id", "energy_consumed_kwh", "total_cost", "message_id", "driver_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "charge_completion",
                message_id=message_id or "",
                info=missing_info,
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
                status="completed",
            )

            # 更新充电点状态为活跃
            self.db_manager.update_charging_point_status(cp_id=cp_id, status=Status.ACTIVE.value)

            self.logger.info(
                f"充电完成: CP {cp_id}, 会话 {session_id}, 消耗电量: {energy_consumed}kWh, 费用: €{total_cost}"
            )

            return MessageFormatter.create_response_message(
                cp_type="charge_completion_response",
                message_id=message_id,
                status="success",
                info=f"充电完成通知已处理，充电点 {cp_id} 状态已更新为活跃",
            )
        except Exception as e:
            self.logger.error(f"处理充电完成通知失败: {e}")
            return self._create_failure_response(
                "charge_completion",
                message_id=message_id,
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
        missing_info = self._check_missing_fields(
            message, ["id", "failure_info", "message_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "fault_notification",
                message_id=message_id or "",
                info=missing_info,
            )

        try:
            # 更新充电点状态为故障
            self.db_manager.update_charging_point_status(cp_id=cp_id, status=Status.FAULTY.value)

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
            return self._create_failure_response(
                "fault_notification",
                message_id=message_id,
                info=f"故障通知处理失败: {e}",
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
        missing_info = self._check_missing_fields(
            message, ["id", "status", "message_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "status_update",
                message_id=message_id or "",
                info=missing_info,
            )

        # 验证状态值是否有效
        valid_statuses = [Status.ACTIVE.value, Status.STOPPED.value, Status.DISCONNECTED.value, Status.CHARGING.value, Status.FAULTY.value]
        if new_status not in valid_statuses:
            return self._create_failure_response(
                "status_update",
                message_id=message_id,
                info=f"无效的状态值: {new_status}。有效状态: {', '.join(valid_statuses)}",
            )

        try:
            # 更新数据库中的状态
            self.db_manager.update_charging_point_status(cp_id=cp_id, status=new_status)

            self.logger.info(f"充电点 {cp_id} 状态已更新为: {new_status}")

            # 如果状态为故障，记录故障信息
            if new_status == Status.FAULTY.value:
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
            return self._create_failure_response(
                "status_update",
                message_id=message_id,
                info=f"状态更新失败: {e}",
            )

    def _handle_available_cps_request(self, client_id, message):
        """处理可用充电点请求"""
        self.logger.info(f"收到来自 {client_id} 的可用充电点请求...")

        message_id = message.get("message_id")
        driver_id = message.get("driver_id")
        missing_info = self._check_missing_fields(
            message, ["message_id", "driver_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "available_cps",
                message_id=message_id or "",
                info=missing_info,
            )
        try:
            # 获取所有充电点
            charging_points = self.get_all_registered_charging_points()

            # 过滤可用充电点（状态为ACTIVE的）
            available_cps = [
                {
                    "id": cp["id"],
                    "location": cp["location"],
                    "price_per_kwh": cp["price_per_kwh"],
                    "status": cp["status"],
                }
                for cp in charging_points
                if cp["status"] == Status.ACTIVE.value
            ]

            self.logger.info(f"Found {len(available_cps)} available charging points")

            return {
                "type": "available_cps_response",
                "message_id": message_id,
                "status": "success",
                "driver_id": driver_id,
                "charging_points": available_cps,
                "timestamp": int(time.time()),
            }

        except Exception as e:
            self.logger.error(f"处理可用充电点请求失败: {e}")
            return {
                "type": "available_cps_response",
                "message_id": message_id,
                "status": "failure",
                "driver_id": driver_id,
                "error": str(e),
                "timestamp": int(time.time()),
            }

    def _handle_authorization_message(
        self, cp_id, client_id, message
    ):  # TODO: implement
        """
        处理来自司机应用程序或充电点本身的充电授权请求。
        需要验证充电点是否可用，并决定是否授权。
        成功授权后，需要向充电点和司机应用程序发送授权通知。
        """
        pass

    def _handle_recovery_message(self, client_id, message):
        """
        处理充电点在故障修复后发送的恢复通知。
        需要更新其状态，并可能重新启用其服务。
        """
        self.logger.info(f"收到来自 {client_id} 的恢复通知...")

        cp_id = message.get("id")
        recovery_info = message.get("recovery_info", "故障已修复")
        message_id = message.get("message_id")
        missing_info = self._check_missing_fields(
            message, ["id", "message_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "recovery_response",
                message_id=message_id or "",
                info=missing_info,
            )
        

        try:
            # 更新充电点状态为活跃
            self.db_manager.update_charging_point_status(cp_id=cp_id, status=Status.ACTIVE.value)

            self.logger.info(f"充电点 {cp_id} 已恢复: {recovery_info}")

            return MessageFormatter.create_response_message(
                cp_type="recovery_response",
                message_id=message_id,
                status="success",
                info=f"恢复通知已处理，充电点 {cp_id} 状态已更新为活跃",
            )
        except Exception as e:
            self.logger.error(f"处理恢复通知失败: {e}")
            return self._create_failure_response(
                cp_type="recovery_response",
                message_id=message_id,
                status="failure",
                info=f"恢复通知处理失败: {e}",
            )

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

    def _send_charging_status_to_driver(self, driver_id, charging_data):
        """
        向指定司机发送充电状态更新
        """
        self.logger.debug(f"向司机 {driver_id} 发送充电状态更新: {charging_data}")
        self.logger.warning(
            "此功能尚未实现，需要通过消息队列或其他方式发送给司机应用程序"
        )

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
                "timestamp": int(time.time()),
            }

            # 发送给Monitor
            self._send_message_to_client(monitor_client_id, start_charging_message)
            self.logger.info(
                f"启动充电命令已发送给Monitor: CP {cp_id}, 会话 {session_id}"
            )
            return True

        except Exception as e:
            self.logger.error(f"发送启动充电命令失败: {e}")
            return False
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

    def _handle_manual_command(self, cp_id, command):  # TODO: implement
        """
        处理来自管理员的手动命令，如启动或停止充电点。
        这些命令需要通过消息队列发送到相应的充电点。
        """
        pass


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    db_connection = SqliteConnection("ev_central.db")
    socket_server = None  # Placeholder, should be an instance of MySocketServer
    charging_points_connections = {}  # Placeholder for actual connections
    client_to_ref = {}  # Placeholder for actual client to reference mapping

    message_dispatcher = MessageDispatcher(
        logger=logger,
        db_manager=db_connection,
        socket_server=socket_server,
        charging_points_connections=charging_points_connections,
        client_to_ref=client_to_ref,
    )
    # Example usage
    example_message = {
        "type": "register_request",
        "id": "CP123",
        "message_id": 1,
        "cp_id": "CP123",
        "location": "123 Main St",
        "price_per_kwh": 0.15,
    }
    response = message_dispatcher.dispatch_message("client1", example_message)
    print(response)
