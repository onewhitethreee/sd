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
from Common.Database.SqliteConnection import SqliteConnection
from Common.Message.MessageFormatter import MessageFormatter
from Common.Config.CustomLogger import CustomLogger
from Common.Config.ConfigManager import ConfigManager
from Common.Network.MySocketServer import MySocketServer
from Common.Config.Status import Status
from Core.Central.ChargingPoint import ChargingPoint
from Core.Central.ChargingSession import ChargingSession


class MessageDispatcher:
    def __init__(
        self,
        logger: CustomLogger,
        db_manager: SqliteConnection,
        socket_server,
    ):
        self.logger = logger
        self.db_manager = db_manager
        self.socket_server: MySocketServer = socket_server

        # 使用新的ChargingPoint和ChargingSession管理器
        self.charging_point_manager = ChargingPoint(logger, db_manager)
        self.charging_session_manager = ChargingSession(logger, db_manager)

        # Driver连接映射
        self._driver_connections = {}  # {driver_id: client_id}
        self._client_to_driver = {}  # {client_id: driver_id}

        self.handlers = {
            "register_request": self._handle_register_message,
            "heartbeat_request": self._handle_heartbeat_message,
            "charge_request": self._handle_charge_request_message,
            "stop_charging_request": self._handle_stop_charging_request,
            "charging_data": self._handle_charging_data_message,
            "charge_completion": self._handle_charge_completion_message,
            "fault_notification": self._handle_fault_notification_message,
            "status_update": self._handle_status_update_message,
            "available_cps_request": self._handle_available_cps_request,
            "recovery_notification": self._handle_recovery_message,
            "manual_command": self._handle_manual_command,
            # "authorization_request": self._handle_authorization_message,  # TODO: implement
        }

    def dispatch_message(self, client_id, message):
        handler = self.handlers.get(message.get("type"))
        if not handler:
            return self._create_failure_response(
                message.get("type"), message.get("message_id", ""), "未知消息类型"
            )

        response = handler(client_id, message)
        return response

    def _create_failure_response(
        self, message_type: str, message_id, info: str
    ) -> dict:
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
        max_charging_rate_kw = message.get("max_charging_rate_kw", 11.0)
        message_id = message.get("message_id")

        missing_info = self._check_missing_fields(
            message, ["id", "location", "price_per_kwh", "message_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "register",
                message_id=message_id,
                info=missing_info,
            )

        # 使用ChargingPoint管理器注册充电桩
        success, error_msg = self.charging_point_manager.register_charging_point(
            cp_id, location, price_per_kwh, max_charging_rate_kw
        )

        if not success:
            return MessageFormatter.create_response_message(
                cp_type="register_response",
                message_id=message_id,
                status="failure",
                info=f"注册失败: {error_msg}",
            )

        # 更新连接映射, 将CP设置为ACTIVE
        self.charging_point_manager.update_charging_point_connection(cp_id, client_id)

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
        cp_id = message.get("id")

        if not cp_id:
            return self._create_failure_response(
                "heartbeat",
                message_id=message.get("message_id", ""),
                info="heartbeat 缺少充电桩ID",
            )

        # 检查充电桩是否已注册
        if self.charging_point_manager.is_charging_point_registered(cp_id):
            try:
                # 更新连接信息
                self.charging_point_manager.update_charging_point_connection(
                    cp_id, client_id
                )
                self._show_registered_charging_points()

                return MessageFormatter.create_response_message(
                    cp_type="heartbeat_response",
                    message_id=message.get("message_id", ""),
                    status="success",
                    info="heartbeat更新最后连接时间成功",
                )
            except Exception as e:
                # TODO 这里如果更新不成功需要设置为faulty吗
                return self._create_failure_response(
                    "heartbeat",
                    message_id=message.get("message_id", ""),
                    info=f"Failed to update last connection time: {e}",
                )
        else:
            return self._create_failure_response(
                "heartbeat",
                message_id=message.get("message_id", ""),
                info=f"Charging point {cp_id} is not registered with heartbeat message.",
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

        # 注册Driver连接（如果尚未注册）
        if driver_id not in self._driver_connections:
            self._driver_connections[driver_id] = client_id
            self._client_to_driver[client_id] = driver_id
            self.logger.info(f"已注册Driver连接: {driver_id} -> {client_id}")

        # 检查充电点是否已注册且可用
        if not self.charging_point_manager.is_charging_point_registered(cp_id):
            return MessageFormatter.create_response_message(
                cp_type="charge_request_response",
                message_id=message_id,
                status="failure",
                info=f"充电点 {cp_id} 未注册",
            )

        cp_status = self.charging_point_manager.get_charging_point_status(cp_id)

        if cp_status != Status.ACTIVE.value:
            return self._create_failure_response(
                "charge_request",
                message_id=message_id,
                info=f"充电点 {cp_id} 当前状态为 {cp_status}，无法进行充电",
            )

        # 授权充电请求
        self.logger.info(f"授权充电请求: CP {cp_id}, Driver {driver_id}")

        try:
            # 使用ChargingSession管理器创建充电会话
            session_id, error_msg = (
                self.charging_session_manager.create_charging_session(cp_id, driver_id)
            )

            if not session_id:
                raise Exception(error_msg or "创建充电会话失败")

            # 更新充电点状态为充电中
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=Status.CHARGING.value
            )

            # 向Monitor发送启动充电命令
            self._send_start_charging_to_monitor(cp_id, session_id, driver_id)

            # 创建响应并agregar cp_id (requerido por el Driver)
            response = MessageFormatter.create_response_message(
                cp_type="charge_request_response",
                message_id=message_id,
                status="success",
                info=f"充电请求已授权，充电点 {cp_id} 开始为司机 {driver_id} 充电，会话ID: {session_id}",
                session_id=session_id,
            )
            response["cp_id"] = cp_id  # Agregar cp_id a la respuesta
            return response
        except Exception as e:
            self.logger.error(f"授权充电请求失败: {e}")
            return self._create_failure_response(
                "charge_request",
                message_id=message_id,
                info=f"授权失败: {e}",
            )

    def _handle_stop_charging_request(self, client_id, message):
        """处理停止充电请求"""
        self.logger.info(f"正在处理来自 {client_id} 的停止充电请求...")

        session_id = message.get("session_id")
        cp_id = message.get("cp_id")
        driver_id = message.get("driver_id")
        message_id = message.get("message_id")

        missing_info = self._check_missing_fields(
            message, ["session_id", "cp_id", "driver_id", "message_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "stop_charging",
                message_id=message_id,
                info=missing_info,
            )

        try:
            # 验证会话存在
            session_info = self.charging_session_manager.get_charging_session(
                session_id
            )
            if not session_info:
                return self._create_failure_response(
                    "stop_charging",
                    message_id=message_id,
                    info=f"充电会话 {session_id} 不存在",
                )

            # 向Monitor发送停止充电命令
            self._send_stop_charging_to_monitor(cp_id, session_id, driver_id)

            # # 立即更新充电点状态为活跃
            # # 这样用户可以看到charging point立即可用，而不需要等待charge_completion消息
            # self.charging_point_manager.update_charging_point_status(
            #     cp_id=cp_id, status=Status.ACTIVE.value
            # )

            # self.logger.info(f"停止充电命令已发送: CP {cp_id}, 会话 {session_id}，状态已更新为ACTIVE")

            # 创建响应并agregar cp_id (para consistencia)
            response = MessageFormatter.create_response_message(
                cp_type="stop_charging_response",
                message_id=message_id,
                status="success",
                info=f"停止充电请求已处理，充电点 {cp_id} 已更新为活跃状态",
                session_id=session_id,
            )
            response["cp_id"] = cp_id  # Agregar cp_id a la respuesta
            return response
        except Exception as e:
            self.logger.error(f"处理停止充电请求失败: {e}")
            return self._create_failure_response(
                "stop_charging",
                message_id=message_id,
                info=f"处理失败: {e}",
            )

    def _handle_charging_data_message(self, client_id, message):
        """
        处理充电点在充电过程中实时发送的电量消耗和费用信息。
        这些数据需要更新到内部状态和数据库，并显示在监控面板上。
        """
        self.logger.info(f"正在处理来自 {client_id} 的充电数据...")

        cp_id = message.get("cp_id")
        session_id = message.get("session_id")
        energy_consumed_kwh = message.get("energy_consumed_kwh")
        total_cost = message.get("total_cost")
        charging_rate = message.get("charging_rate")
        message_id = message.get("message_id")

        missing_info = self._check_missing_fields(
            message,
            [
                "cp_id",
                "session_id",
                "energy_consumed_kwh",
                "total_cost",
                "charging_rate",
                "message_id",
            ],
        )
        if missing_info:
            return self._create_failure_response(
                "charging_data",
                message_id=message_id or "",
                info=missing_info,
            )

        try:
            # 使用ChargingSession管理器更新充电会话
            self.charging_session_manager.update_charging_session(
                session_id=session_id,
                energy_consumed_kwh=energy_consumed_kwh,
                total_cost=total_cost,
                status="in_progress",
            )

            # 获取充电会话信息
            session_info = self.charging_session_manager.get_charging_session(
                session_id
            )
            if session_info:
                driver_id = session_info["driver_id"]

                # 发送充电状态更新给Driver
                self._send_charging_status_to_driver(
                    driver_id,
                    {
                        "session_id": session_id,
                        "energy_consumed_kwh": energy_consumed_kwh,
                        "total_cost": total_cost,
                        "charging_rate": charging_rate,
                        "timestamp": int(time.time()),
                    },
                )

                self.logger.info(
                    f"充电数据更新: 会话 {session_id}, 电量: {energy_consumed_kwh}kWh, 费用: €{total_cost}"
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
        session_id = message.get("session_id")
        energy_consumed_kwh = message.get("energy_consumed_kwh")
        total_cost = message.get("total_cost")
        message_id = message.get("message_id")

        missing_info = self._check_missing_fields(
            message,
            [
                "cp_id",
                "session_id",
                "energy_consumed_kwh",
                "total_cost",
                "message_id",
            ],
        )
        if missing_info:
            return self._create_failure_response(
                "charge_completion",
                message_id=message_id or "",
                info=missing_info,
            )

        try:
            # 从会话中获取driver_id
            session_info = self.charging_session_manager.get_charging_session(
                session_id
            )
            if not session_info:
                return MessageFormatter.create_response_message(
                    cp_type="charge_completion_response",
                    message_id=message_id,
                    status="failure",
                    info=f"充电会话 {session_id} 不存在",
                )

            driver_id = session_info.get("driver_id")

            # 使用ChargingSession管理器完成充电会话
            success, session_data = (
                self.charging_session_manager.complete_charging_session(
                    session_id=session_id,
                    energy_consumed_kwh=energy_consumed_kwh,
                    total_cost=total_cost,
                )
            )

            if not success:
                raise Exception("完成充电会话失败")

            # 更新充电点状态为活跃
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=Status.ACTIVE.value
            )

            self.logger.info(
                f"充电完成: CP {cp_id}, 会话 {session_id}, 消耗电量: {energy_consumed_kwh}kWh, 费用: €{total_cost} session_data: {session_data}"
            )

            # 向Driver发送充电完成通知
            if driver_id:
                self._send_charge_completion_to_driver(
                    driver_id,
                    {
                        "session_id": session_id,
                        "cp_id": cp_id,
                        "energy_consumed_kwh": energy_consumed_kwh,
                        "total_cost": total_cost,
                        "timestamp": int(time.time()),
                    },
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
            # 使用ChargingPoint管理器更新充电点状态为故障
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=Status.FAULTY.value
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
        valid_statuses = [
            Status.ACTIVE.value,
            Status.STOPPED.value,
            Status.DISCONNECTED.value,
            Status.CHARGING.value,
            Status.FAULTY.value,
        ]
        if new_status not in valid_statuses:
            return self._create_failure_response(
                "status_update",
                message_id=message_id,
                info=f"无效的状态值: {new_status}。有效状态: {', '.join(valid_statuses)}",
            )

        try:
            # 使用ChargingPoint管理器更新状态
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=new_status
            )

            self.logger.info(f"充电点 {cp_id} 状态已更新为: {new_status}")

            # 如果状态为故障，记录故障信息
            if new_status == Status.FAULTY.value:
                self.logger.warning(f"充电点 {cp_id} 报告故障状态")
                # self.charging_point_manager.update_charging_point_status(
                #     cp_id=cp_id, status=Status.FAULTY.value
                # )
                # self.logger.error(f"充电点 {cp_id} 状态更新为故障")
                

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
        missing_info = self._check_missing_fields(message, ["message_id", "driver_id"])
        if missing_info:
            return self._create_failure_response(
                "available_cps",
                message_id=message_id or "",
                info=missing_info,
            )
        try:
            # 使用ChargingPoint管理器获取可用充电点
            available_cps = self.charging_point_manager.get_available_charging_points()

            # 格式化响应数据
            available_cps_data = [
                {
                    "id": cp["cp_id"],
                    "location": cp["location"],
                    "price_per_kwh": round(cp["price_per_kwh"], 3),
                    "status": cp["status"],
                    "max_charging_rate_kw": round(cp["max_charging_rate_kw"], 3),
                }
                for cp in available_cps
            ]

            self.logger.info(
                f"Found {len(available_cps_data)} available charging points"
            )

            return {
                "type": "available_cps_response",
                "message_id": message_id,
                "status": "success",
                "driver_id": driver_id,
                "charging_points": available_cps_data,
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

    def _handle_authorization_message(self, client_id, message):  # TODO: implement
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
        missing_info = self._check_missing_fields(message, ["id", "message_id"])
        if missing_info:
            return self._create_failure_response(
                "recovery_response",
                message_id=message_id or "",
                info=missing_info,
            )

        try:
            # 使用ChargingPoint管理器更新充电点状态为活跃
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=Status.ACTIVE.value
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
        charging_points = self.charging_point_manager.get_all_charging_points()
        if not charging_points:
            print("No registered charging points found.")
            return

        print("\n" + "╔" + "═" * 60 + "╗")
        print("║" + " Puntos de recarga registrados ".center(60) + "║")
        print("╚" + "═" * 60 + "╝\n")

        for i, cp in enumerate(charging_points, 1):
            print(f"【{i}】 charging point {cp['cp_id']}")
            print(f"    ├─ Location: {cp['location']}")
            print(f"    ├─ Price/kWh: €{cp['price_per_kwh']}/kWh")
            print(f"    ├─ Status: {cp['status']}")
            print(f"    ├─ Max Charging Rate: {cp['max_charging_rate_kw']}kW")
            print(f"    └─ Last Connection: {cp['last_connection_time']}")
            print()

    def _send_charging_status_to_driver(self, driver_id, charging_data):
        """
        向指定司机发送充电状态更新
        """
        try:
            # 查找Driver的客户端连接
            driver_client_id = self._driver_connections.get(driver_id)
            if not driver_client_id:
                self.logger.warning(
                    f"未找到司机 {driver_id} 的连接，无法发送充电状态更新"
                )
                return False

            # 构建充电状态更新消息
            status_message = {
                "type": "charging_status_update",
                "message_id": str(uuid.uuid4()),
                "driver_id": driver_id,
                "session_id": charging_data.get("session_id"),
                "energy_consumed_kwh": charging_data.get("energy_consumed_kwh"),
                "total_cost": charging_data.get("total_cost"),
                "charging_rate": charging_data.get("charging_rate"),
                "timestamp": charging_data.get("timestamp", int(time.time())),
            }

            # 发送给Driver
            self._send_message_to_client(driver_client_id, status_message)
            self.logger.debug(f"充电状态更新已发送给司机 {driver_id}")
            return True

        except Exception as e:
            self.logger.error(f"向司机 {driver_id} 发送充电状态更新失败: {e}")
            return False

    def _send_charge_completion_to_driver(self, driver_id, completion_data):
        """
        向指定司机发送充电完成通知
        """
        try:
            # 查找Driver的客户端连接
            driver_client_id = self._driver_connections.get(driver_id)
            if not driver_client_id:
                self.logger.warning(
                    f"未找到司机 {driver_id} 的连接，无法发送充电完成通知"
                )
                return False

            # 构建充电完成通知消息
            completion_message = {
                "type": "charge_completion_notification",
                "message_id": str(uuid.uuid4()),
                "driver_id": driver_id,
                "session_id": completion_data.get("session_id"),
                "cp_id": completion_data.get("cp_id"),
                "energy_consumed_kwh": completion_data.get("energy_consumed_kwh"),
                "total_cost": completion_data.get("total_cost"),
                "timestamp": completion_data.get("timestamp", int(time.time())),
            }

            # 发送给Driver
            self._send_message_to_client(driver_client_id, completion_message)
            self.logger.info(f"充电完成通知已发送给司机 {driver_id}")
            return True

        except Exception as e:
            self.logger.error(f"向司机 {driver_id} 发送充电完成通知失败: {e}")
            return False

    def _send_start_charging_to_monitor(self, cp_id, session_id, driver_id):
        """
        向Monitor发送启动充电命令
        """
        try:
            # 查找连接到该充电点的Monitor客户端
            monitor_client_id = (
                self.charging_point_manager.get_client_id_for_charging_point(cp_id)
            )
            if not monitor_client_id:
                self.logger.error(f"未找到充电点 {cp_id} 的Monitor连接")
                return False

            # 从数据库获取充电点信息（包括price_per_kwh和max_charging_rate_kw）
            cp_info = self.charging_point_manager.get_charging_point(cp_id)
            price_per_kwh = cp_info.get("price_per_kwh", 0.0) if cp_info else 0.0
            max_charging_rate_kw = (
                cp_info.get("max_charging_rate_kw", 11.0) if cp_info else 11.0
            )

            # 构建启动充电命令
            start_charging_message = {
                "type": "start_charging_command",
                "message_id": str(uuid.uuid4()),
                "cp_id": cp_id,
                "session_id": session_id,
                "driver_id": driver_id,
                "price_per_kwh": price_per_kwh,  # 从数据库获取
                "max_charging_rate_kw": max_charging_rate_kw,  # 从数据库获取
                "timestamp": int(time.time()),
            }

            # 发送给Monitor
            self._send_message_to_client(monitor_client_id, start_charging_message)
            self.logger.info(
                f"启动充电命令已发送给Monitor: CP {cp_id}, 会话 {session_id}, 价格: €{price_per_kwh}/kWh, 最大速率: {max_charging_rate_kw}kW"
            )
            return True

        except Exception as e:
            self.logger.error(f"发送启动充电命令失败: {e}")
            return False

    def _send_stop_charging_to_monitor(self, cp_id, session_id, driver_id):
        """向Monitor发送停止充电命令"""
        try:
            monitor_client_id = self.charging_point_manager.get_client_id_for_charging_point(cp_id)
            if not monitor_client_id:
                self.logger.error(f"未找到充电点 {cp_id} 的Monitor连接")
                return False

            # 构建停止充电命令
            stop_charging_message = {
                "type": "stop_charging_command",
                "message_id": str(uuid.uuid4()),
                "cp_id": cp_id,
                "session_id": session_id,
                "driver_id": driver_id,
                "timestamp": int(time.time()),
            }

            # 发送给Monitor
            self._send_message_to_client(monitor_client_id, stop_charging_message)
            self.logger.info(
                f"停止充电命令已发送给Monitor: CP {cp_id}, 会话 {session_id}"
            )
            return True

        except Exception as e:
            self.logger.error(f"发送停止充电命令失败: {e}")
            return False

    def _send_message_to_client(self, client_id, message):
        """
        向指定Driver 客户端发送消息
        """
        try:
            if self.socket_server:
                self.socket_server.send_to_client(client_id, message)
                self.logger.debug(f"消息已发送给客户端 {client_id}: {message}")
            else:
                self.logger.error("Socket服务器未初始化")
        except Exception as e:
            self.logger.error(f"向客户端 {client_id} 发送消息失败: {e}")

    def _handle_manual_command(self, client_id, message):
        """
        处理来自管理员的手动命令，如启动或停止充电点。
        这些命令需要通过消息队列发送到相应的充电点。

        支持的命令:
        - "stop": 停止指定的CP或所有CPs
        - "resume": 恢复指定的CP或所有CPs

        消息格式:
        {
            "type": "manual_command",
            "message_id": "...",
            "command": "stop" | "resume",
            "cp_id": "CP_ID" | "all",  # "all" 表示所有CPs
            "admin_id": "..."  # 可选，管理员ID
        }
        """
        self.logger.info(f"正在处理来自 {client_id} 的手动命令...")

        command = message.get("command")
        cp_id = message.get("cp_id")
        message_id = message.get("message_id")

        # 检查必要字段
        missing_info = self._check_missing_fields(
            message, ["command", "cp_id", "message_id"]
        )
        if missing_info:
            return self._create_failure_response(
                "manual_command",
                message_id=message_id or "",
                info=missing_info,
            )

        # 验证命令类型
        valid_commands = ["stop", "resume"]
        if command not in valid_commands:
            return self._create_failure_response(
                "manual_command",
                message_id=message_id,
                info=f"无效的命令类型: {command}。有效命令: {', '.join(valid_commands)}",
            )

        try:
            # 判断是针对单个CP还是所有CPs
            if cp_id == "all":
                return self._execute_command_for_all_cps(command, message_id)
            else:
                return self._execute_command_for_single_cp(command, cp_id, message_id)

        except Exception as e:
            self.logger.error(f"执行手动命令失败: {e}")
            return self._create_failure_response(
                "manual_command",
                message_id=message_id,
                info=f"命令执行失败: {e}",
            )

    def _execute_command_for_single_cp(self, command, cp_id, message_id):
        """
        为单个CP执行命令
        """
        # 检查CP是否存在
        if not self.charging_point_manager.is_charging_point_registered(cp_id):
            return self._create_failure_response(
                "manual_command",
                message_id=message_id,
                info=f"充电点 {cp_id} 未注册",
            )

        # 获取CP的客户端连接
        monitor_client_id = self.charging_point_manager.get_client_id_for_charging_point(cp_id)

        if command == "stop":
            return self._stop_charging_point(cp_id, monitor_client_id, message_id)
        elif command == "resume":
            return self._resume_charging_point(cp_id, monitor_client_id, message_id)

    def _execute_command_for_all_cps(self, command, message_id):
        """
        为所有CPs执行命令
        """
        all_cps = self.charging_point_manager.get_all_charging_points()

        if not all_cps:
            return self._create_failure_response(
                "manual_command",
                message_id=message_id,
                info="没有注册的充电点",
            )

        successful_cps = []
        failed_cps = []

        for cp in all_cps:
            cp_id = cp["cp_id"]
            monitor_client_id = self.charging_point_manager.get_client_id_for_charging_point(cp_id)

            try:
                if command == "stop":
                    self._stop_charging_point(cp_id, monitor_client_id, message_id)
                elif command == "resume":
                    self._resume_charging_point(cp_id, monitor_client_id, message_id)

                successful_cps.append(cp_id)
            except Exception as e:
                self.logger.error(f"对CP {cp_id} 执行命令 {command} 失败: {e}")
                failed_cps.append(cp_id)

        # 构建响应信息
        info_parts = []
        if successful_cps:
            info_parts.append(f"成功执行命令的CPs: {', '.join(successful_cps)}")
        if failed_cps:
            info_parts.append(f"执行命令失败的CPs: {', '.join(failed_cps)}")

        status = "success" if not failed_cps else ("partial" if successful_cps else "failure")

        return MessageFormatter.create_response_message(
            cp_type="manual_command_response",
            message_id=message_id,
            status=status,
            info="; ".join(info_parts),
        )

    def _stop_charging_point(self, cp_id, monitor_client_id, message_id):
        """
        停止充电点（设置为STOPPED状态）
        """
        # 检查当前状态，如果正在充电，需要先停止充电
        current_status = self.charging_point_manager.get_charging_point_status(cp_id)

        if current_status == Status.CHARGING.value:
            # 获取正在进行的充电会话
            # 这里需要获取session_id，可能需要从charging_session_manager查询
            # 简化处理：直接更新状态
            self.logger.warning(f"充电点 {cp_id} 正在充电，将被强制停止")

        # 更新充电点状态为STOPPED
        self.charging_point_manager.update_charging_point_status(
            cp_id=cp_id, status=Status.STOPPED.value
        )

        # 向Monitor发送停止命令
        if monitor_client_id:
            stop_command_message = {
                "type": "stop_cp_command",
                "message_id": str(uuid.uuid4()),
                "cp_id": cp_id,
                "timestamp": int(time.time()),
            }
            self._send_message_to_client(monitor_client_id, stop_command_message)

        self.logger.info(f"充电点 {cp_id} 已被设置为停止状态")

        return MessageFormatter.create_response_message(
            cp_type="manual_command_response",
            message_id=message_id,
            status="success",
            info=f"充电点 {cp_id} 已停止，状态设置为 '出服务'",
        )

    def _resume_charging_point(self, cp_id, monitor_client_id, message_id):
        """
        恢复充电点（设置为ACTIVE状态）
        """
        current_status = self.charging_point_manager.get_charging_point_status(cp_id)

        # 只有STOPPED或FAULTY状态的CP可以恢复
        if current_status not in [Status.STOPPED.value, Status.FAULTY.value]:
            return self._create_failure_response(
                "manual_command",
                message_id=message_id,
                info=f"充电点 {cp_id} 当前状态为 {current_status}，无法恢复",
            )

        # 更新充电点状态为ACTIVE
        self.charging_point_manager.update_charging_point_status(
            cp_id=cp_id, status=Status.ACTIVE.value
        )

        # 向Monitor发送恢复命令
        if monitor_client_id:
            resume_command_message = {
                "type": "resume_cp_command",
                "message_id": str(uuid.uuid4()),
                "cp_id": cp_id,
                "timestamp": int(time.time()),
            }
            self._send_message_to_client(monitor_client_id, resume_command_message)

        self.logger.info(f"充电点 {cp_id} 已恢复为活跃状态")

        return MessageFormatter.create_response_message(
            cp_type="manual_command_response",
            message_id=message_id,
            status="success",
            info=f"充电点 {cp_id} 已恢复，状态设置为 'ACTIVE'",
        )


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    db_connection = SqliteConnection("ev_central.db")
    socket_server = None  # Placeholder, should be an instance of MySocketServer

    message_dispatcher = MessageDispatcher(
        logger=logger,
        db_manager=db_connection,
        socket_server=socket_server,
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
