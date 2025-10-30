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
            "stop_charging_command": self._handle_stop_charging_command,
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
            self.logger.debug(f"Dispatching message from {source}: {msg_type} {message}")

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
        self.logger.info("Received registration response from Central: ", message)
        if message.get("status") == "success":
            self.logger.info("Registration successful.")
        else:
            self.logger.error(
                f"Registration failed: {message.get('reason', 'Unknown')}"
            )
        return True

    def _handle_heartbeat_response(self, message):
        """处理来自Central的心跳响应"""
        self.logger.debug("Received heartbeat response from Central: ", message)
        if message.get("status") == "success":
            self.logger.debug("Monitor成功接收心跳响应")
        else:
            self.logger.warning("Heartbeat not acknowledged by Central")
        return True

    def _handle_start_charging_command(self, message):
        """处理来自Central的启动充电命令"""
        self.logger.info("Received start charging command from Central.")
        return self.monitor._handle_start_charging_command(message)

    def _handle_stop_charging_command(self, message):
        """处理来自Central的停止充电命令"""
        self.logger.info("Received stop charging command from Central.")
        cp_id = message.get("cp_id")
        session_id = message.get("session_id")

        # 向Engine发送停止充电命令
        stop_message = {
            "type": "stop_charging_command",
            "message_id": message.get("message_id"),
            "cp_id": cp_id,
            "session_id": session_id,
        }

        if self.monitor.engine_conn_mgr and self.monitor.engine_conn_mgr.is_connected:
            self.monitor.engine_conn_mgr.send(stop_message)
            self.logger.info(f"停止充电命令已转发给Engine: CP {cp_id}")
            return True
        else:
            self.logger.error("Engine连接不可用")
            return False
    # TODO 这下面的逻辑需要完善
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
        """
        处理来自Engine的健康检查响应

        Según especificaciones:
        - Monitor_OK and Engine_OK => Activado (Verde)
        - Monitor_OK and Engine_KO => Averiado (Rojo)
        """
        self.logger.debug(f"Health check response from Engine: {message}")

        # 更新最后一次收到健康检查响应的时间
        # 这是防止健康检查超时的关键
        self.monitor._update_last_health_response()

        engine_status = message.get("engine_status")

        # Monitor está OK (recibiendo health check), verificar estado de Engine
        if engine_status == "FAULTY":
            # Monitor OK + Engine KO = FAULTY
            self.logger.warning("Engine reports FAULTY status.")
            self.monitor.update_cp_status("FAULTY")
        elif engine_status == "ACTIVE":
            self.logger.debug("Engine reports ACTIVE status.")
            # Monitor OK + Engine OK = ACTIVE (solo si Central también conectado)
            if self.monitor.central_conn_mgr and self.monitor.central_conn_mgr.is_connected:
                # Ambos Monitor y Engine OK, y Central conectado => ACTIVE
                if self.monitor._current_status != "ACTIVE":
                    self.monitor.update_cp_status("ACTIVE")
            else:
                # Monitor OK, Engine OK, pero Central desconectado
                self.logger.warning("Engine is ACTIVE but Central is not connected")
                self.monitor.update_cp_status("FAULTY")

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
