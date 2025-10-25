"""
Monitor消息分发器
负责处理来自Central和Engine的所有消息，包括：
- 来自Central的消息：start_charging_command等
- 来自Engine的消息：health_check_response, charging_data, charge_completion等
- 连接状态变化：CONNECTED, DISCONNECTED
"""

import uuid


class MonitorMessageDispatcher:
    """
    Monitor消息分发器
    统一处理来自Central和Engine的消息，提供清晰的消息处理接口
    """

    def __init__(self, logger, monitor):
        """
        初始化MonitorMessageDispatcher

        Args:
            logger: 日志记录器
            monitor: EV_CP_M实例，用于访问Monitor的业务逻辑
        """
        self.logger = logger
        self.monitor = monitor

        # 来自Central的消息处理器
        self.central_handlers = {
            "register_response": self._handle_register_response,
            "heartbeat_response": self._handle_heartbeat_response,
            "start_charging_command": self._handle_start_charging_command,
            "charging_data_response": self._handle_charging_data_response,
            "fault_notification_response": self._handle_fault_notification_response,
            "status_update_response": self._handle_status_update_response,
            "charge_completion_response": self._handle_charge_completion_response,
        }

        # 来自Engine的消息处理器
        self.engine_handlers = {
            "health_check_response": self._handle_health_check_response,
            "charging_data": self._handle_charging_data_from_engine,
            "charge_completion": self._handle_charging_completion_from_engine,
            "command_response": self._handle_command_response,
        }

    def dispatch_message(self, source, message):
        """
        分发消息到对应的处理器

        Args:
            source: 消息来源 ("Central" 或 "Engine")
            message: 消息字典

        Returns:
            bool: 处理是否成功
        """
        try:
            msg_type = message.get("type")
            self.logger.debug(f"Dispatching message from {source}: {msg_type}")

            if source == "Central":
                handler = self.central_handlers.get(msg_type)
            elif source == "Engine":
                handler = self.engine_handlers.get(msg_type)
            else:
                self.logger.warning(f"Unknown message source: {source}")
                return False

            if handler:
                return handler(message)
            else:
                self.logger.warning(f"Unknown message type from {source}: {msg_type}")
                return False

        except Exception as e:
            self.logger.error(f"Error dispatching message from {source}: {e}")
            return False

    # ==================== Central消息处理器 ====================

    def _handle_register_response(self, message):
        """处理来自Central的注册响应"""
        self.logger.info("Received registration response from Central.")
        if message.get("status") == "success":
            self.logger.info("Registration successful.")
        else:
            self.logger.error(f"Registration failed: {message.get('reason', 'Unknown')}")
        return True

    def _handle_heartbeat_response(self, message):
        """处理来自Central的心跳响应"""
        if message.get("status") == "success":
            self.logger.debug("Monitor成功接收心跳响应")
        else:
            self.logger.warning("Heartbeat not acknowledged by Central")
        return True

    def _handle_start_charging_command(self, message):
        """处理来自Central的启动充电命令"""
        self.logger.info("Received start charging command from Central.")
        return self.monitor._handle_start_charging_command(message)

    def _handle_charging_data_response(self, message):
        """处理来自Central的充电数据响应"""
        self.logger.debug(f"Charging data response from Central: {message}")
        return True

    def _handle_fault_notification_response(self, message):
        """处理来自Central的故障通知响应"""
        self.logger.error(f"Fault notification response from Central: {message}")
        return True

    def _handle_status_update_response(self, message):
        """处理来自Central的状态更新响应"""
        self.logger.debug(f"Status update response from Central: {message}")
        return True

    def _handle_charge_completion_response(self, message):
        """处理来自Central的充电完成响应"""
        self.logger.debug(f"Charge completion response from Central: {message}")
        return True

    # ==================== Engine消息处理器 ====================

    def _handle_health_check_response(self, message):
        """处理来自Engine的健康检查响应"""
        self.logger.debug(f"Health check response from Engine: {message}")

        engine_status = message.get("engine_status")
        if engine_status == "FAULTY":
            self.logger.warning("Engine reports FAULTY status.")
            self.monitor.update_cp_status("FAULTY")
        elif engine_status == "ACTIVE":
            self.logger.debug("Engine reports ACTIVE status.")
            # 如果当前状态是故障，尝试恢复（Central也需正常）
            if (
                self.monitor._current_status == "FAULTY"
                and self.monitor.central_conn_mgr.is_connected
            ):
                self.monitor.update_cp_status("ACTIVE")

        return True

    def _handle_charging_data_from_engine(self, message):
        """处理来自Engine的充电数据"""
        self.logger.debug("Received charging data from Engine.")
        return self.monitor._handle_charging_data_from_engine(message)

    def _handle_charging_completion_from_engine(self, message):
        """处理来自Engine的充电完成通知"""
        self.logger.info("Received charging completion from Engine.")
        return self.monitor._handle_charging_completion_from_engine(message)
    def _handle_command_response(self, message):
        """处理来自Engine的命令响应"""
        self.logger.debug(f"Command response from Engine: {message}")
        return True

