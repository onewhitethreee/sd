"""
Engine消息分发器
负责处理来自Monitor的所有消息，包括：
- health_check_request: 健康检查请求
- stop_command: 停止充电命令
- resume_command: 恢复运行命令
- start_charging_command: 开始充电命令
"""

import time


class EngineMessageDispatcher:
    """
    Engine消息分发器
    将消息处理逻辑从EV_CP_E中分离出来，提供清晰的消息处理接口
    """

    def __init__(self, logger, engine):
        """
        初始化EngineMessageDispatcher

        Args:
            logger: 日志记录器
            engine: EV_CP_E实例，用于访问Engine的业务逻辑
        """
        self.logger = logger
        self.engine = engine  # 不使用类型注解以避免循环导入

        # 消息处理器映射
        self.handlers = {
            "health_check_request": self._handle_health_check,
            "stop_command": self._handle_stop_command,
            "resume_command": self._handle_resume_command,
            "start_charging_command": self._handle_start_charging_command,
            "stop_charging_command": self._handle_stop_charging_command,
        }

    def dispatch_message(self, message):
        """
        分发消息到对应的处理器

        Args:
            message: 消息字典

        Returns:
            dict: 响应消息
        """
        try:
            msg_type = message.get("type")
            self.logger.debug(f"Dispatching message type: {msg_type}")

            handler = self.handlers.get(msg_type)
            if handler:
                return handler(message)
            else:
                self.logger.warning(f"Unknown message type: {msg_type}")
                return self._create_error_response(
                    message.get("message_id"), "Unknown message type"
                )

        except Exception as e:
            self.logger.error(f"Error dispatching message: {e}")
            return self._create_error_response(message.get("message_id"), str(e))

    def _create_error_response(self, message_id, error_msg):
        """
        创建错误响应消息

        Args:
            message_id: 原始消息ID
            error_msg: 错误信息

        Returns:
            dict: 错误响应消息
        """
        return {
            "type": "error_response",
            "message_id": message_id,
            "error": error_msg,
        }

    def _handle_health_check(self, message):
        """
        处理健康检查请求

        Args:
            message: 健康检查请求消息

        Returns:
            dict: 健康检查响应消息
        """

        response = {
            "type": "health_check_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "engine_status": self.engine.get_current_status(),
            "is_charging": self.engine.is_charging,
        }

        self.logger.debug(f"Health check response prepared: {response}")
        return response

    def _handle_stop_command(self, message):
        """
        处理停止命令

        Args:
            message: 停止命令消息

        Returns:
            dict: 命令响应消息
        """
        self.logger.info("Processing stop command")

        if self.engine.is_charging:
            self.engine._stop_charging_session()

        response = {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "message": "Stop command executed",
        }
        return response

    def _handle_resume_command(self, message):
        """
        处理恢复命令

        Args:
            message: 恢复命令消息

        Returns:
            dict: 命令响应消息
        """
        self.logger.info("Processing resume command")

        if not self.engine.running:
            self.engine.running = True
            self.logger.info("Engine resumed operation")

        return {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "message": "Resume command executed",
        }

    def _handle_start_charging_command(self, message):
        """
        处理开始充电命令

        Args:
            message: 开始充电命令消息，包含：
                - session_id: 充电会话ID
                - driver_id: 司机/电动车ID
                - price_per_kwh: 每度电价格（从Central获取）
                - max_charging_rate_kw: 最大充电速率（从Central获取）

        Returns:
            dict: 命令响应消息
        """
        self.logger.info("Processing start charging command")

        # 获取会话ID（由Central通过Monitor提供）
        session_id = message.get("session_id")
        if not session_id:
            self.logger.error("Start charging command missing session_id")
            return {
                "type": "command_response",
                "message_id": message.get("message_id"),
                "status": "failure",
                "message": "Missing session_id",
            }
        driver_id = message.get("driver_id", "unknown_driver")
        price_per_kwh = message.get("price_per_kwh", 0.0)  # 从Central获取价格
        max_charging_rate_kw = message.get(
            "max_charging_rate_kw", 11.0
        )  # 从Central获取最大充电速率

        # 检查是否已在充电
        if self.engine.is_charging:
            return {
                "type": "command_response",
                "message_id": message.get("message_id"),
                "status": "failure",
                "message": "Already charging",
                "session_id": self.engine.current_session["session_id"],
            }

        # 启动充电会话，传递price_per_kwh和max_charging_rate_kw
        success = self.engine._start_charging_session(
            driver_id, session_id, price_per_kwh, max_charging_rate_kw
        )
        return {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success" if success else "failure",
            "message": "Charging started" if success else "Failed to start charging",
            "session_id": session_id if success else None,
        }

    def _handle_stop_charging_command(self, message):
        """
        处理停止充电命令

        Args:
            message: 停止充电命令消息，包含：
                - session_id: 充电会话ID
                - cp_id: 充电点ID

        Returns:
            dict: 命令响应消息
        """
        self.logger.info("Processing stop charging command")

        session_id = message.get("session_id")

        # 验证会话ID匹配
        if (
            self.engine.current_session
            and self.engine.current_session["session_id"] == session_id
        ):
            self.engine._stop_charging_session()
            self.logger.info(f"充电会话 {session_id} 已停止")
            return {
                "type": "command_response",
                "message_id": message.get("message_id"),
                "status": "success",
                "message": "Charging stopped",
                "session_id": session_id,
            }
        else:
            self.logger.warning(f"会话ID不匹配或无活跃会话: {session_id}")
            return {
                "type": "command_response",
                "message_id": message.get("message_id"),
                "status": "failure",
                "message": "No active charging session or session ID mismatch",
                "session_id": session_id,
            }


# TODO 修复在停止central模块的情况下Engine还会继续charge
