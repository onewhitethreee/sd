"""
Central 消息分发器

负责处理来自 Monitor、Driver 和 Admin 的所有消息。
这是整个系统的核心消息处理中心，协调充电点、司机和充电会话。

主要职责：
1. 处理充电点注册和状态管理
2. 处理司机充电请求和会话管理
3. 转发充电数据和状态更新
4. 处理管理员命令
"""

import os
import sys
import time
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Database.SqliteConnection import SqliteConnection
from Core.Central.ChargingPoint import ChargingPoint
from Core.Central.ChargingSession import ChargingSession
from Core.Central.DriverManager import DriverManager

from Common.Message.MessageFormatter import MessageFormatter
from Common.Message.MessageTypes import MessageTypes, ResponseStatus, MessageFields
from Common.Config.CustomLogger import CustomLogger
from Common.Config.ConfigManager import ConfigManager
from Common.Network.MySocketServer import MySocketServer
from Common.Config.Status import Status
from Common.Queue.KafkaManager import KafkaTopics


class MessageDispatcher:
    def __init__(
        self,
        logger: CustomLogger,
        db_manager: SqliteConnection,
        socket_server,
        kafka_manager=None,
    ):
        self.logger = logger
        self.socket_server: MySocketServer = socket_server
        self.kafka_manager = kafka_manager  # Kafka管理器用于向Driver发送响应

        # 使用新的ChargingPoint和ChargingSession管理器
        self.charging_point_manager = ChargingPoint(logger, db_manager)
        self.charging_session_manager = ChargingSession(logger, db_manager)

        # 使用DriverManager管理Driver连接
        self.driver_manager = DriverManager(logger, self.charging_session_manager)

        # 幂等性处理：跟踪已处理的 message_id（用于Kafka消息去重）
        self._processed_message_ids = set()  # {message_id}
        self._max_processed_ids = 10000  # 最多保留10000个ID，防止内存无限增长

        # 待授权的充电点列表：{cp_id: {client_id, timestamp, message_id}}
        self._pending_authorizations = {}

        # 消息处理器映射（使用消息类型常量）
        self.handlers = {
            # Monitor 消息
            MessageTypes.AUTH_REQUEST: self._handle_auth_request,
            MessageTypes.REGISTER_REQUEST: self._handle_register_message,
            MessageTypes.HEARTBEAT_REQUEST: self._handle_heartbeat_message,
            MessageTypes.FAULT_NOTIFICATION: self._handle_fault_notification_message,
            MessageTypes.STATUS_UPDATE: self._handle_status_update_message,
            MessageTypes.RECOVERY_NOTIFICATION: self._handle_recovery_message,
            MessageTypes.CHARGING_DATA: self._handle_charging_data_message,
            MessageTypes.CHARGE_COMPLETION: self._handle_charge_completion_message,

            # Driver 消息
            MessageTypes.CHARGE_REQUEST: self._handle_charge_request_message,
            MessageTypes.STOP_CHARGING_REQUEST: self._handle_stop_charging_request,
            MessageTypes.AVAILABLE_CPS_REQUEST: self._handle_available_cps_request,
            MessageTypes.CHARGING_HISTORY_REQUEST: self._handle_charging_history_request,

            # Admin 消息
            MessageTypes.MANUAL_COMMAND: self._handle_manual_command,
        }

    def dispatch_message(self, client_id, message):
        """
        分发消息到对应的处理器

        Args:
            client_id: 客户端连接ID（对于来自Kafka的Driver消息，这是driver_id）
            message: 消息字典

        Returns:
            dict: 响应消息（如果需要）
        """
        msg_type = message.get(MessageFields.TYPE)
        handler = self.handlers.get(msg_type)

        if not handler:
            self.logger.warning(
                f"Unknown message type: {msg_type}. "
                f"Client: {client_id}, Message ID: {message.get(MessageFields.MESSAGE_ID)}"
            )
            response = self._create_failure_response(
                msg_type,
                message.get(MessageFields.MESSAGE_ID, ""),
                "未知消息类型"
            )
            self._send_response_to_client(client_id, response, msg_type)
            return response

        try:
            response = handler(client_id, message)
            # 对于Driver请求，通过Kafka发送响应
            if msg_type in [MessageTypes.CHARGE_REQUEST, MessageTypes.STOP_CHARGING_REQUEST,
                           MessageTypes.AVAILABLE_CPS_REQUEST, MessageTypes.CHARGING_HISTORY_REQUEST]:
                self._send_response_to_driver_via_kafka(client_id, response, msg_type)
            return response
        except Exception as e:
            self.logger.error(
                f"Error handling message {msg_type} from {client_id}: {e}. "
                f"Message: {message}"
            )
            response = self._create_failure_response(
                msg_type,
                message.get(MessageFields.MESSAGE_ID, ""),
                f"处理消息时发生错误: {str(e)}"
            )
            self._send_response_to_client(client_id, response, msg_type)
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

    def _create_success_response(
        self, message_type: str, message_id, info: str, **extra_fields
    ) -> dict:
        """创建成功响应"""
        response = MessageFormatter.create_response_message(
            cp_type=f"{message_type}_response",
            message_id=message_id,
            status="success",
            info=info,
        )
        # 添加额外字段
        response.update(extra_fields)
        return response

    def _send_response_to_driver_via_kafka(self, driver_id, response, msg_type):
        """通过Kafka向Driver发送响应（使用统一的响应主题）"""
        if not self.kafka_manager:
            self.logger.warning("Kafka manager not initialized, cannot send response to Driver")
            return

        try:
            # 获取统一的Driver响应主题
            # 所有Driver共享同一个主题，通过消息中的driver_id字段区分不同Driver
            driver_topic = KafkaTopics.get_driver_response_topic()

            # 确保响应消息包含driver_id字段（关键！）
            if "driver_id" not in response:
                response["driver_id"] = driver_id
                self.logger.debug(f"Added driver_id to response: {driver_id}")

            success = self.kafka_manager.produce_message(
                driver_topic,
                response
            )
            if success:
                self.logger.debug(f"Response sent to unified topic {driver_topic} for Driver {driver_id}: {response.get('type')}")
            else:
                self.logger.error(f"Failed to send response to Driver {driver_id} on unified topic {driver_topic}")
        except Exception as e:
            self.logger.error(f"Error sending response to Driver {driver_id} via Kafka: {e}")

    def _send_response_to_client(self, client_id, response, msg_type):
        """向客户端发送响应（智能选择Socket或Kafka）"""
        # 如果是Driver消息，使用Kafka
        if msg_type in [MessageTypes.CHARGE_REQUEST, MessageTypes.STOP_CHARGING_REQUEST,
                       MessageTypes.AVAILABLE_CPS_REQUEST, MessageTypes.CHARGING_HISTORY_REQUEST]:
            self._send_response_to_driver_via_kafka(client_id, response, msg_type)
        # 否则使用Socket（ChargingPoint/Monitor）
        elif self.socket_server:
            try:
                self.socket_server.send_to_client(client_id, response)
            except Exception as e:
                self.logger.error(f"Failed to send response to client {client_id}: {e}")

    def _is_duplicate_message(self, message_id: str) -> bool:
        """
        检查消息是否已处理（用于幂等性）

        返回: True 如果消息已处理过，False 如果是新消息
        """
        if message_id in self._processed_message_ids:
            return True

        # 记录新的 message_id
        self._processed_message_ids.add(message_id)

        # 防止内存无限增长：如果超过最大值，清除最旧的一半
        if len(self._processed_message_ids) > self._max_processed_ids:
            # 转为列表，保留后半部分（较新的ID）
            ids_list = list(self._processed_message_ids)
            self._processed_message_ids = set(ids_list[len(ids_list) // 2 :])
            self.logger.debug(
                f"已处理消息ID数量超过限制，清理到 {len(self._processed_message_ids)} 个"
            )

        return False

    def _check_missing_fields(self, message: dict, required_fields: list):
        missing = [field for field in required_fields if message.get(field) is None]
        if missing:
            return f"消息中缺少必要字段: {', '.join(missing)}"
        return None

    def _validate_and_extract_fields(self, message: dict, required_fields: list, message_type: str):
        """
        验证消息字段并提取，如果验证失败返回错误响应

        返回: (success: bool, data_or_response: dict)
        - 如果成功: (True, {extracted_fields})
        - 如果失败: (False, error_response)
        """
        missing_info = self._check_missing_fields(message, required_fields)
        if missing_info:
            return False, self._create_failure_response(
                message_type,
                message_id=message.get("message_id", ""),
                info=missing_info,
            )

        # 提取字段
        extracted = {field: message.get(field) for field in required_fields}
        return True, extracted

    def _build_notification_message(self, message_type: str, **fields) -> dict:
        """
        构建通用的通知消息

        参数:
            message_type: 消息类型（使用 MessageTypes 常量）
            **fields: 消息字段（自动添加 message_id 和 timestamp）
        """
        message = {
            MessageFields.TYPE: message_type,
            MessageFields.MESSAGE_ID: str(uuid.uuid4()),
            MessageFields.TIMESTAMP: int(time.time()),
        }
        message.update(fields)
        return message

    def _send_notification_to_driver(self, driver_id: str, message: dict) -> bool:
        """
        向指定司机发送通知消息

        返回: 是否成功发送
        """
        try:
            driver_client_id = self.driver_manager.get_driver_client_id(driver_id)
            if not driver_client_id:
                self.logger.warning(
                    f"未找到司机 {driver_id} 的连接，无法发送通知: {message.get('type')}"
                )
                return False

            self._send_message_to_client(driver_client_id, message)
            self.logger.debug(f"通知已发送给司机 {driver_id}: {message.get('type')}")
            return True

        except Exception as e:
            self.logger.error(f"向司机 {driver_id} 发送通知失败: {e}")
            return False

    def _send_command_to_monitor(self, cp_id: str, command_message: dict) -> bool:
        """
        向Monitor发送命令消息

        返回: 是否成功发送
        """
        try:
            monitor_client_id = self.charging_point_manager.get_client_id_for_charging_point(cp_id)
            if not monitor_client_id:
                self.logger.error(f"未找到充电点 {cp_id} 的Monitor连接")
                return False

            self._send_message_to_client(monitor_client_id, command_message)
            self.logger.info(
                f"{command_message.get('type')} 已发送给Monitor: CP {cp_id}"
            )
            return True

        except Exception as e:
            self.logger.error(f"发送命令到Monitor失败: {e}")
            return False

    def _handle_auth_request(self, client_id, message):
        """
        处理充电点的认证请求
        
        认证请求会被添加到待授权列表，等待管理员手动批准。
        只有经过授权的充电点才能进行注册。
        """
        self.logger.info(f"收到来自 {client_id} 的认证请求...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["id", "message_id"], "auth_request"
        )
        if not success:
            return data  # 返回错误响应

        cp_id = data["id"]
        message_id = data["message_id"]

        # 检查是否已经授权
        if cp_id in self._pending_authorizations:
            self.logger.warning(f"充电点 {cp_id} 已存在待授权请求，等待管理员批准")
            return self._create_failure_response(
                "auth_request", message_id, "认证请求已存在，等待管理员批准"
            )

        # 添加到待授权列表
        self._pending_authorizations[cp_id] = {
            "client_id": client_id,
            "timestamp": time.time(),
            "message_id": message_id,
        }

        self.logger.info(
            f"充电点 {cp_id} 的认证请求已添加到待授权列表，等待管理员批准"
        )
        self.logger.info(f"使用 AdminCLI 的 'authorize <cp_id>' 命令来批准")

        # 返回pending状态响应（不是成功，而是等待批准）
        return self._create_success_response(
            "auth_request", message_id, "认证请求已收到，等待管理员批准"
        )

    def authorize_charging_point(self, cp_id: str) -> bool:
        """
        授权充电点（由AdminCLI调用）
        
        Args:
            cp_id: 充电点ID
            
        Returns:
            bool: 是否成功授权
        """
        if cp_id not in self._pending_authorizations:
            self.logger.warning(f"充电点 {cp_id} 不在待授权列表中")
            return False

        # 从待授权列表中移除
        auth_info = self._pending_authorizations.pop(cp_id)
        self.logger.info(f"充电点 {cp_id} 已获得授权")

        # 向Monitor发送授权响应
        auth_response = self._create_success_response(
            "auth_response",
            auth_info["message_id"],
            f"充电点 {cp_id} 已获得授权，现在可以进行注册"
        )
        auth_response[MessageFields.CP_ID] = cp_id

        self._send_message_to_client(auth_info["client_id"], auth_response)
        self.logger.info(f"授权响应已发送给充电点 {cp_id}")

        return True

    def get_pending_authorizations(self) -> list:
        """
        获取待授权的充电点列表（供AdminCLI显示）
        
        Returns:
            list: 待授权充电点列表 [{cp_id, client_id, timestamp}]
        """
        return [
            {
                "cp_id": cp_id,
                "client_id": info["client_id"],
                "timestamp": info["timestamp"],
                "pending_time": time.time() - info["timestamp"],
            }
            for cp_id, info in self._pending_authorizations.items()
        ]

    def _handle_register_message(self, client_id, message):
        """专门处理充电桩的注册请求"""
        self.logger.info(f"正在处理来自 {client_id} 的注册请求...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["id", "location", "price_per_kwh", "message_id"], "register"
        )
        if not success:
            return data  # 返回错误响应

        cp_id = data["id"]
        location = data["location"]
        price_per_kwh = data["price_per_kwh"]
        message_id = data["message_id"]

        # 检查是否已经授权
        if cp_id in self._pending_authorizations:
            return self._create_failure_response(
                "register", message_id, f"充电点 {cp_id} 尚未获得授权，请先通过认证"
            )

        # 注册充电桩
        success, error_msg = self.charging_point_manager.register_charging_point(
            cp_id, location, price_per_kwh
        )

        if not success:
            return self._create_failure_response(
                "register", message_id, f"注册失败: {error_msg}"
            )

        # 更新连接映射
        self.charging_point_manager.update_charging_point_connection(cp_id, client_id)
        self._show_registered_charging_points()

        return self._create_success_response(
            "register", message_id, f"charging point {cp_id} registered successfully."
        )

    def _handle_heartbeat_message(self, client_id, message):
        """处理充电桩发送的心跳消息，更新其最后连接时间"""
        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["id", "message_id"], "heartbeat"
        )
        if not success:
            return data

        cp_id = data["id"]
        message_id = data["message_id"]

        # 检查充电桩是否已注册
        if not self.charging_point_manager.is_charging_point_registered(cp_id):
            return self._create_failure_response(
                "heartbeat",
                message_id,
                f"Charging point {cp_id} is not registered with heartbeat message.",
            )

        try:
            # 更新连接信息
            self.charging_point_manager.update_charging_point_connection(
                cp_id, client_id
            )
            self._show_registered_charging_points()

            return self._create_success_response(
                "heartbeat", message_id, "heartbeat更新最后连接时间成功"
            )
        except Exception as e:
            return self._create_failure_response(
                "heartbeat", message_id, f"Failed to update last connection time: {e}"
            )

    def _handle_charge_request_message(self, client_id, message):
        """处理来自司机应用程序或充电点本身的充电请求"""
        self.logger.info(f"正在处理来自 {client_id} 的充电请求...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["cp_id", "driver_id", "message_id"], "charge_request"
        )
        if not success:
            return data

        cp_id = data["cp_id"]
        driver_id = data["driver_id"]
        message_id = data["message_id"]

        # 注册Driver连接（如果尚未注册）
        if not self.driver_manager.is_driver_connected(driver_id):
            self.driver_manager.register_driver_connection(driver_id, client_id)

        # 检查充电点是否已注册且可用
        if not self.charging_point_manager.is_charging_point_registered(cp_id):
            response = self._create_failure_response(
                "charge_request", message_id, f"充电点 {cp_id} 未注册"
            )
            response["driver_id"] = driver_id  # 确保失败响应也包含driver_id
            return response

        cp_status = self.charging_point_manager.get_charging_point_status(cp_id)
        if cp_status != Status.ACTIVE.value:
            response = self._create_failure_response(
                "charge_request",
                message_id,
                f"充电点 {cp_id} 当前状态为 {cp_status}，无法进行充电",
            )
            response["driver_id"] = driver_id  # 确保失败响应也包含driver_id
            return response

        # 授权充电请求
        self.logger.info(f"授权充电请求: CP {cp_id}, Driver {driver_id}")

        try:
            # 创建充电会话
            session_id, error_msg = (
                self.charging_session_manager.create_charging_session(cp_id, driver_id)
            )
            if not session_id:
                raise Exception(error_msg or "创建充电会话失败")

            # 更新充电点状态为充电中
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=Status.CHARGING.value
            )

            # 注意：不再需要手动维护 _driver_active_sessions
            # 活跃会话通过 ChargingSession 数据库查询
            self.logger.debug(
                f"Driver {driver_id} 开始充电会话 {session_id}"
            )

            # 向Monitor发送启动充电命令
            self._send_start_charging_to_monitor(cp_id, session_id, driver_id)

            # 创建响应（包含driver_id以便Driver能正确过滤消息）
            return self._create_success_response(
                "charge_request",
                message_id,
                f"充电请求已授权，充电点 {cp_id} 开始为司机 {driver_id} 充电，会话ID: {session_id}",
                session_id=session_id,
                cp_id=cp_id,
                driver_id=driver_id,  # 添加driver_id字段
            )
        except Exception as e:
            self.logger.error(f"授权充电请求失败: {e}")
            response = self._create_failure_response(
                "charge_request", message_id, f"授权失败: {e}"
            )
            response["driver_id"] = driver_id  # 确保失败响应也包含driver_id
            return response

    def _handle_stop_charging_request(self, client_id, message):
        """处理停止充电请求"""
        self.logger.info(f"正在处理来自 {client_id} 的停止充电请求...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["session_id", "cp_id", "driver_id", "message_id"], "stop_charging"
        )
        if not success:
            return data

        session_id = data["session_id"]
        cp_id = data["cp_id"]
        driver_id = data["driver_id"]
        message_id = data["message_id"]

        try:
            # 验证会话存在
            session_info = self.charging_session_manager.get_charging_session(
                session_id
            )
            if not session_info:
                response = self._create_failure_response(
                    "stop_charging", message_id, f"充电会话 {session_id} 不存在"
                )
                response["driver_id"] = driver_id  # 确保失败响应也包含driver_id
                return response

            # 向Monitor发送停止充电命令
            self._send_stop_charging_to_monitor(cp_id, session_id, driver_id)

            return self._create_success_response(
                "stop_charging",
                message_id,
                f"停止充电请求已处理，充电点 {cp_id} 已更新为活跃状态",
                session_id=session_id,
                cp_id=cp_id,
                driver_id=driver_id,  # 添加driver_id字段
            )
        except Exception as e:
            self.logger.error(f"处理停止充电请求失败: {e}")
            response = self._create_failure_response(
                "stop_charging", message_id, f"处理失败: {e}"
            )
            response["driver_id"] = driver_id  # 确保失败响应也包含driver_id
            return response

    def _handle_charging_data_message(self, client_id, message):
        """处理充电点在充电过程中实时发送的电量消耗和费用信息（改进版：支持幂等性）"""
        self.logger.info(f"正在处理来自 {client_id} 的充电数据...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message,
            [
                "cp_id",
                "session_id",
                "energy_consumed_kwh",
                "total_cost",
                "message_id",
            ],
            "charging_data",
        )
        if not success:
            return data

        session_id = data["session_id"]
        energy_consumed_kwh = data["energy_consumed_kwh"]
        total_cost = data["total_cost"]
        message_id = data["message_id"]

        # 幂等性检查：如果消息已处理过，直接返回成功（避免重复处理）
        if self._is_duplicate_message(message_id):
            self.logger.debug(f"消息 {message_id} 已处理过，跳过（幂等性）")
            return self._create_success_response(
                "charging_data", message_id, "充电数据已处理（重复消息）"
            )

        try:
            # 更新充电会话
            self.charging_session_manager.update_charging_session(
                session_id=session_id,
                energy_consumed_kwh=energy_consumed_kwh,
                total_cost=total_cost,
                status="in_progress",
            )

            # 获取充电会话信息并发送状态更新给Driver
            session_info = self.charging_session_manager.get_charging_session(
                session_id
            )
            if session_info:
                driver_id = session_info["driver_id"]
                self._send_charging_status_to_driver(
                    driver_id,
                    {
                        "session_id": session_id,
                        "energy_consumed_kwh": energy_consumed_kwh,
                        "total_cost": total_cost,
                        "timestamp": int(time.time()),
                    },
                )

                self.logger.info(
                    f"充电数据更新: 会话 {session_id}, 电量: {energy_consumed_kwh}kWh, 费用: €{total_cost}"
                )

            return self._create_success_response(
                "charging_data", message_id, "充电数据已处理"
            )
        except Exception as e:
            self.logger.error(f"处理充电数据失败: {e}")
            return self._create_failure_response(
                "charging_data", message_id, f"处理失败: {e}"
            )

    def _handle_charge_completion_message(self, client_id, message):
        """处理充电完成的通知（改进版：支持幂等性）"""
        self.logger.info(f"正在处理来自 {client_id} 的充电完成通知...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message,
            [
                "cp_id",
                "session_id",
                "energy_consumed_kwh",
                "total_cost",
                "message_id",
            ],
            "charge_completion",
        )
        if not success:
            return data

        cp_id = data["cp_id"]
        session_id = data["session_id"]
        energy_consumed_kwh = data["energy_consumed_kwh"]
        total_cost = data["total_cost"]
        message_id = data["message_id"]

        # 幂等性检查：如果消息已处理过，直接返回成功（避免重复处理）
        if self._is_duplicate_message(message_id):
            self.logger.debug(f"消息 {message_id} 已处理过，跳过（幂等性）")
            return self._create_success_response(
                "charge_completion", message_id, "充电完成通知已处理（重复消息）"
            )

        try:
            # 从会话中获取driver_id
            session_info = self.charging_session_manager.get_charging_session(
                session_id
            )
            if not session_info:
                return self._create_failure_response(
                    "charge_completion", message_id, f"充电会话 {session_id} 不存在"
                )

            driver_id = session_info.get("driver_id")

            # 完成充电会话
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

            # 注意：不再需要手动从 _driver_active_sessions 移除
            # 会话状态已在数据库中标记为 "completed"
            self.logger.debug(
                f"Driver {driver_id} 的会话 {session_id} 已完成"
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

            return self._create_success_response(
                "charge_completion",
                message_id,
                f"充电完成通知已处理，充电点 {cp_id} 状态已更新为活跃",
            )
        except Exception as e:
            self.logger.error(f"处理充电完成通知失败: {e}")
            return self._create_failure_response(
                "charge_completion", message_id, f"处理失败: {e}"
            )

    def _handle_fault_notification_message(self, client_id, message):
        """处理充电点发送的故障或异常通知"""
        self.logger.warning(f"收到来自 {client_id} 的故障通知...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["id", "failure_info", "message_id"], "fault_notification"
        )
        if not success:
            return data

        cp_id = data["id"]
        failure_info = data["failure_info"]
        message_id = data["message_id"]

        try:
            # 更新充电点状态为故障
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=Status.FAULTY.value
            )

            self.logger.error(f"充电点 {cp_id} 故障: {failure_info}")

            # TODO: 在这里可以添加通知维护人员的逻辑

            return self._create_success_response(
                "fault_notification",
                message_id,
                f"故障通知已记录，充电点 {cp_id} 状态已更新为故障",
            )
        except Exception as e:
            self.logger.error(f"处理故障通知失败: {e}")
            return self._create_failure_response(
                "fault_notification", message_id, f"故障通知处理失败: {e}"
            )

    def _handle_status_update_message(self, client_id, message):
        """处理充电点发送的状态更新消息"""
        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["id", "status", "message_id"], "status_update"
        )
        if not success:
            return data

        cp_id = data["id"]
        new_status = data["status"]
        message_id = data["message_id"]

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
                message_id,
                f"无效的状态值: {new_status}。有效状态: {', '.join(valid_statuses)}",
            )

        try:
            # 更新状态
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=new_status
            )

            self.logger.info(f"充电点 {cp_id} 状态已更新为: {new_status}")

            # 如果状态为故障，记录故障信息
            if new_status == Status.FAULTY.value:
                self.logger.warning(f"充电点 {cp_id} 报告故障状态")

            return self._create_success_response(
                "status_update", message_id, f"充电点 {cp_id} 状态已更新为 {new_status}"
            )
        except Exception as e:
            self.logger.error(f"更新充电点状态失败: {e}")
            return self._create_failure_response(
                "status_update", message_id, f"状态更新失败: {e}"
            )

    def _handle_available_cps_request(self, client_id, message):
        """处理可用充电点请求"""
        self.logger.info(f"收到来自 {client_id} 的可用充电点请求...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["message_id", "driver_id"], "available_cps"
        )
        if not success:
            return data

        message_id = data["message_id"]
        driver_id = data["driver_id"]

        try:
            # 获取可用充电点
            available_cps = self.charging_point_manager.get_available_charging_points()

            # 格式化响应数据
            available_cps_data = [
                {
                    "id": cp["cp_id"],
                    "location": cp["location"],
                    "price_per_kwh": round(cp["price_per_kwh"], 3),
                    "status": cp["status"],
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

    def _handle_charging_history_request(self, client_id, message):
        """处理充电历史查询请求"""
        self.logger.info(f"收到来自 {client_id} 的充电历史查询请求...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["message_id", "driver_id"], "charging_history"
        )
        if not success:
            return data

        message_id = data["message_id"]
        driver_id = data["driver_id"]
        limit = message.get("limit", None)  # 可选的记录数量限制

        try:
            # 从ChargingSession获取充电历史
            history = self.charging_session_manager.get_driver_charging_history(
                driver_id, limit=limit
            )

            # 格式化历史记录
            history_data = [
                {
                    "session_id": record["session_id"],
                    "cp_id": record["cp_id"],
                    "start_time": record["start_time"],
                    "end_time": record["end_time"],
                    "energy_consumed_kwh": round(record["energy_consumed_kwh"], 3),
                    "total_cost": round(record["total_cost"], 2),
                    "status": record["status"],
                }
                for record in history
            ]

            self.logger.info(
                f"Found {len(history_data)} charging history records for driver {driver_id}"
            )

            return {
                "type": "charging_history_response",
                "message_id": message_id,
                "status": "success",
                "driver_id": driver_id,
                "history": history_data,
                "count": len(history_data),
                "timestamp": int(time.time()),
            }

        except Exception as e:
            self.logger.error(f"处理充电历史请求失败: {e}")
            return {
                "type": "charging_history_response",
                "message_id": message_id,
                "status": "failure",
                "driver_id": driver_id,
                "error": str(e),
                "timestamp": int(time.time()),
            }

    def _handle_recovery_message(self, client_id, message):
        """处理充电点在故障修复后发送的恢复通知"""
        self.logger.info(f"收到来自 {client_id} 的恢复通知...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["id", "message_id"], "recovery_response"
        )
        if not success:
            return data

        cp_id = data["id"]
        message_id = data["message_id"]
        recovery_info = message.get("recovery_info", "故障已修复")

        try:
            # 更新充电点状态为活跃
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=Status.ACTIVE.value
            )

            self.logger.info(f"充电点 {cp_id} 已恢复: {recovery_info}")

            return self._create_success_response(
                "recovery_response",
                message_id,
                f"恢复通知已处理，充电点 {cp_id} 状态已更新为活跃",
            )
        except Exception as e:
            self.logger.error(f"处理恢复通知失败: {e}")
            return self._create_failure_response(
                "recovery_response", message_id, f"恢复通知处理失败: {e}"
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
            print(f"[{i}] charging point {cp['cp_id']}")
            print(f"    ├─ Location: {cp['location']}")
            print(f"    ├─ Price/kWh: €{cp['price_per_kwh']}/kWh")
            print(f"    ├─ Status: {cp['status']}")
            print(f"    └─ Last Connection: {cp['last_connection_time']}")
            print()

    def _send_charging_status_to_driver(self, driver_id, charging_data):
        """向指定司机发送充电状态更新（通过统一的响应主题）"""
        message = self._build_notification_message(
            "charging_status_update",
            driver_id=driver_id,  # 关键：消息必须包含driver_id字段
            session_id=charging_data.get("session_id"),
            energy_consumed_kwh=charging_data.get("energy_consumed_kwh"),
            total_cost=charging_data.get("total_cost"),
        )
        # 发送到统一的Driver响应主题
        if self.kafka_manager:
            driver_topic = KafkaTopics.get_driver_response_topic()
            success = self.kafka_manager.produce_message(
                driver_topic,
                message
            )
            if success:
                self.logger.debug(f"Charging status sent to unified topic {driver_topic} for Driver {driver_id}")
            return success
        else:
            self.logger.warning("Kafka not available, cannot send charging status to Driver")
            return False

    def _send_charge_completion_to_driver(self, driver_id, completion_data):
        """向指定司机发送充电完成通知（通过统一的响应主题）"""
        message = self._build_notification_message(
            "charge_completion",
            driver_id=driver_id,  # 关键：消息必须包含driver_id字段
            session_id=completion_data.get("session_id"),
            cp_id=completion_data.get("cp_id"),
            energy_consumed_kwh=completion_data.get("energy_consumed_kwh"),
            total_cost=completion_data.get("total_cost"),
        )
        # 发送到统一的Driver响应主题
        if self.kafka_manager:
            driver_topic = KafkaTopics.get_driver_response_topic()
            success = self.kafka_manager.produce_message(
                driver_topic,
                message
            )
            if success:
                self.logger.info(f"Charge completion notification sent to unified topic {driver_topic} for Driver {driver_id}")
            return success
        else:
            self.logger.warning("Kafka not available, cannot send charge completion to Driver")
            return False

    def _send_start_charging_to_monitor(self, cp_id, session_id, driver_id):
        """向Monitor发送启动充电命令"""
        # 从数据库获取充电点信息
        cp_info = self.charging_point_manager.get_charging_point(cp_id)
        price_per_kwh = cp_info.get("price_per_kwh", 0.0) if cp_info else 0.0
       

        message = self._build_notification_message(
            "start_charging_command",
            cp_id=cp_id,
            session_id=session_id,
            driver_id=driver_id,
            price_per_kwh=price_per_kwh,
        )

        success = self._send_command_to_monitor(cp_id, message)
        if success:
            self.logger.info(
                f"启动充电命令详情: CP {cp_id}, 会话 {session_id}, 价格: €{price_per_kwh}/kWh"
            )
        return success

    def _send_stop_charging_to_monitor(self, cp_id, session_id, driver_id):
        """向Monitor发送停止充电命令"""
        message = self._build_notification_message(
            "stop_charging_command",
            cp_id=cp_id,
            session_id=session_id,
            driver_id=driver_id,
        )
        return self._send_command_to_monitor(cp_id, message)

    def handle_driver_disconnect(self, client_id):
        """
        处理Driver断开连接

        当Driver断开连接时：
        1. 查找该Driver正在进行的所有充电会话
        2. 停止所有相关的充电会话
        3. 通知相关的充电桩
        4. 清理连接映射
        """
        # 委托给DriverManager处理断开连接
        driver_id, active_session_ids = self.driver_manager.handle_driver_disconnect(
            client_id
        )

        if not driver_id:
            self.logger.debug(f"客户端 {client_id} 不是Driver，跳过Driver断开连接处理")
            return None

        # 停止所有活跃会话
        if active_session_ids:
            for session_id in active_session_ids:
                self._stop_session_due_to_driver_disconnect(session_id, driver_id)

        return driver_id

    def _stop_session_due_to_driver_disconnect(self, session_id, driver_id):
        """
        由于Driver断开连接而停止充电会话
        """
        try:
            # 获取会话信息
            session_info = self.charging_session_manager.get_charging_session(session_id)
            if not session_info:
                self.logger.warning(f"会话 {session_id} 不存在，可能已经结束")
                return

            cp_id = session_info.get("cp_id")
            energy_consumed_kwh = session_info.get("energy_consumed_kwh", 0.0)
            total_cost = session_info.get("total_cost", 0.0)

            self.logger.info(
                f"由于Driver {driver_id} 断开连接，停止会话 {session_id} (CP: {cp_id})"
            )

            # 向Monitor发送停止充电命令
            self._send_stop_charging_to_monitor(cp_id, session_id, driver_id)

            # 完成充电会话（标记为由于断开连接而终止）
            success, _ = self.charging_session_manager.complete_charging_session(
                session_id=session_id,
                energy_consumed_kwh=energy_consumed_kwh,
                total_cost=total_cost,
            )

            if success:
                # 更新充电点状态为活跃
                self.charging_point_manager.update_charging_point_status(
                    cp_id=cp_id, status=Status.ACTIVE.value
                )
                self.logger.info(
                    f"会话 {session_id} 已因Driver断开而终止，CP {cp_id} 状态更新为ACTIVE"
                )

            # 注意：不再需要手动从 _driver_active_sessions 移除
            # 会话状态已在数据库中更新

        except Exception as e:
            self.logger.error(f"停止会话 {session_id} 失败: {e}")

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
        处理来自管理员的手动命令，如启动或停止充电点

        支持的命令:
        - "stop": 停止指定的CP或所有CPs
        - "resume": 恢复指定的CP或所有CPs
        """
        self.logger.info(f"正在处理来自 {client_id} 的手动命令...")

        # 验证并提取字段
        success, data = self._validate_and_extract_fields(
            message, ["command", "cp_id", "message_id"], "manual_command"
        )
        if not success:
            return data

        command = data["command"]
        cp_id = data["cp_id"]
        message_id = data["message_id"]

        # 验证命令类型
        valid_commands = ["stop", "resume"]
        if command not in valid_commands:
            return self._create_failure_response(
                "manual_command",
                message_id,
                f"无效的命令类型: {command}。有效命令: {', '.join(valid_commands)}",
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
                "manual_command", message_id, f"命令执行失败: {e}"
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
        """停止充电点（设置为STOPPED状态）"""
        # 检查当前状态
        current_status = self.charging_point_manager.get_charging_point_status(cp_id)
        if current_status == Status.CHARGING.value:
            self.logger.warning(f"充电点 {cp_id} 正在充电，将被强制停止")

        # 更新充电点状态为STOPPED
        self.charging_point_manager.update_charging_point_status(
            cp_id=cp_id, status=Status.STOPPED.value
        )

        # 向Monitor发送停止命令
        if monitor_client_id:
            stop_command_message = self._build_notification_message(
                "stop_cp_command", cp_id=cp_id
            )
            self._send_message_to_client(monitor_client_id, stop_command_message)

        self.logger.info(f"充电点 {cp_id} 已被设置为停止状态")

        return self._create_success_response(
            "manual_command", message_id, f"充电点 {cp_id} 已停止，状态设置为 '出服务'"
        )

    def _resume_charging_point(self, cp_id, monitor_client_id, message_id):
        """恢复充电点（设置为ACTIVE状态）"""
        current_status = self.charging_point_manager.get_charging_point_status(cp_id)

        # 只有STOPPED或FAULTY状态的CP可以恢复
        if current_status not in [Status.STOPPED.value, Status.FAULTY.value]:
            return self._create_failure_response(
                "manual_command",
                message_id,
                f"充电点 {cp_id} 当前状态为 {current_status}，无法恢复",
            )

        # 更新充电点状态为ACTIVE
        self.charging_point_manager.update_charging_point_status(
            cp_id=cp_id, status=Status.ACTIVE.value
        )

        # 向Monitor发送恢复命令
        if monitor_client_id:
            resume_command_message = self._build_notification_message(
                "resume_cp_command", cp_id=cp_id
            )
            self._send_message_to_client(monitor_client_id, resume_command_message)

        self.logger.info(f"充电点 {cp_id} 已恢复为活跃状态")

        return self._create_success_response(
            "manual_command", message_id, f"充电点 {cp_id} 已恢复，状态设置为 'ACTIVE'"
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


