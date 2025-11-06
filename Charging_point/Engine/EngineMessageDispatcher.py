"""
Engine消息分发器

负责处理来自Monitor的所有消息，包括：
- 健康检查请求
- 启动/停止充电命令

所有处理器方法返回响应字典，通过MySocketServer自动发送回Monitor。
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Message.MessageTypes import MessageTypes, ResponseStatus, MessageFields


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
        self.engine = engine

        # 消息处理器映射（使用消息类型常量）
        self.handlers = {
            MessageTypes.INIT_CP_ID: self._handle_init_cp_id,
            MessageTypes.HEALTH_CHECK_REQUEST: self._handle_health_check,
            MessageTypes.START_CHARGING_COMMAND: self._handle_start_charging_command,
            MessageTypes.STOP_CHARGING_COMMAND: self._handle_stop_charging_command,
            MessageTypes.RESUME_CP_COMMAND: self._handle_resume_cp_command,
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
            msg_type = message.get(MessageFields.TYPE)
            self.logger.debug(f"Dispatching message type: {msg_type}")

            handler = self.handlers.get(msg_type)
            if handler:
                return handler(message)
            else:
                self.logger.warning(f"Unknown message type: {msg_type}")
                return self._create_error_response(
                    message.get(MessageFields.MESSAGE_ID),
                    f"Unknown message type: {msg_type}",
                )

        except Exception as e:
            self.logger.error(f"Error dispatching message: {e}")
            return self._create_error_response(
                message.get(MessageFields.MESSAGE_ID), str(e)
            )

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
            MessageFields.TYPE: MessageTypes.ERROR_RESPONSE,
            MessageFields.MESSAGE_ID: message_id,
            MessageFields.STATUS: ResponseStatus.ERROR,
            MessageFields.ERROR: error_msg,
        }

    def _handle_init_cp_id(self, message):
        """
        处理CP_ID初始化请求（来自Monitor）

        Args:
            message: 初始化消息，包含：
                - cp_id: 充电桩ID

        Returns:
            dict: 初始化响应消息
        """
        cp_id = message.get(MessageFields.CP_ID)

        if not cp_id:
            self.logger.error("INIT_CP_ID message missing cp_id field")
            return {
                MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
                MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
                MessageFields.STATUS: ResponseStatus.FAILURE,
                MessageFields.MESSAGE: "Missing cp_id",
            }

        # 设置CP_ID
        success = self.engine.set_cp_id(cp_id)

        return {
            MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
            MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
            MessageFields.STATUS: (
                ResponseStatus.SUCCESS if success else ResponseStatus.FAILURE
            ),
            MessageFields.MESSAGE: (
                f"CP_ID set to {cp_id}" if success else "CP_ID already initialized"
            ),
            MessageFields.CP_ID: cp_id,
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
            MessageFields.TYPE: MessageTypes.HEALTH_CHECK_RESPONSE,
            MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
            MessageFields.STATUS: ResponseStatus.SUCCESS,
            MessageFields.ENGINE_STATUS: self.engine.get_current_status(),
            MessageFields.IS_CHARGING: self.engine.is_charging,
        }

        self.logger.debug(f"Health check response prepared: {response}")
        return response

    def _handle_start_charging_command(self, message):
        """
        处理开始充电命令

        Args:
            message: 开始充电命令消息，包含：
                - session_id: 充电会话ID
                - driver_id: 司机/电动车ID
                - price_per_kwh: 每度电价格（从Central获取）

        Returns:
            dict: 命令响应消息
        """
        self.logger.info("Processing start charging command")

        # 获取会话ID（由Central通过Monitor提供）
        session_id = message.get(MessageFields.SESSION_ID)
        if not session_id:
            self.logger.error("Start charging command missing session_id")
            return {
                MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
                MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
                MessageFields.STATUS: ResponseStatus.FAILURE,
                MessageFields.MESSAGE: "Missing session_id",
            }

        driver_id = message.get(MessageFields.DRIVER_ID, "unknown_driver")
        price_per_kwh = message.get(MessageFields.PRICE_PER_KWH, 0.0)

        # 检查是否已在充电
        if self.engine.is_charging:
            return {
                MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
                MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
                MessageFields.STATUS: ResponseStatus.FAILURE,
                MessageFields.MESSAGE: "Already charging",
                MessageFields.SESSION_ID: self.engine.current_session["session_id"],
            }

        # 启动充电会话
        success = self.engine._start_charging_session(
            driver_id, session_id, price_per_kwh
        )
        return {
            MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
            MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
            MessageFields.STATUS: (
                ResponseStatus.SUCCESS if success else ResponseStatus.FAILURE
            ),
            MessageFields.MESSAGE: (
                "Charging started" if success else "Failed to start charging"
            ),
            MessageFields.SESSION_ID: session_id if success else None,
        }

    def _handle_stop_charging_command(self, message):
        """
        处理停止充电命令

        支持两种停止模式：
        1. 正常停止：提供具体的session_id，验证后停止
        2. 紧急停止：session_id为None，强制停止当前任何活跃会话

        Args:
            message: 停止充电命令消息，包含：
                - session_id: 充电会话ID（可以为None表示紧急停止）
                - cp_id: 充电点ID

        Returns:
            dict: 命令响应消息
        """
        self.logger.info("Processing stop charging command")

        session_id = message.get(MessageFields.SESSION_ID)

        # 情况1: session_id为None - 紧急停止（例如FAULTY状态或Monitor断开）
        if session_id is None:
            if self.engine.current_session:
                stopped_session_id = self.engine.current_session["session_id"]
                self.engine._stop_charging_session()
                self.logger.info(
                    f"紧急停止充电会话: {stopped_session_id} (session_id=None)"
                )
                return {
                    MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
                    MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
                    MessageFields.STATUS: ResponseStatus.SUCCESS,
                    MessageFields.MESSAGE: f"Emergency stop: charging session {stopped_session_id} stopped",
                    MessageFields.SESSION_ID: stopped_session_id,
                }
            else:
                self.logger.debug("紧急停止命令收到，但没有活跃会话")
                return {
                    MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
                    MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
                    MessageFields.STATUS: ResponseStatus.SUCCESS,
                    MessageFields.MESSAGE: "No active session to stop",
                    MessageFields.SESSION_ID: None,
                }

        # 情况2: 提供了具体的session_id - 验证后停止
        if (
            self.engine.current_session
            and self.engine.current_session["session_id"] == session_id
        ):
            self.engine._stop_charging_session()
            self.logger.info(f"充电会话 {session_id} 已停止")
            return {
                MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
                MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
                MessageFields.STATUS: ResponseStatus.SUCCESS,
                MessageFields.MESSAGE: "Charging stopped",
                MessageFields.SESSION_ID: session_id,
            }
        else:
            self.logger.warning(f"会话ID不匹配或无活跃会话: {session_id}")
            return {
                MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
                MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
                MessageFields.STATUS: ResponseStatus.FAILURE,
                MessageFields.MESSAGE: "No active charging session or session ID mismatch",
                MessageFields.SESSION_ID: session_id,
            }

    def _handle_resume_cp_command(self, message):
        """
        处理来自Central的恢复充电点命令

        这个命令由Central管理员发出，具有最高优先级。
        它会强制清除Engine的手动FAULTY模式，即使是通过CLI设置的。

        Args:
            message: 恢复命令消息，包含：
                - cp_id: 充电点ID

        Returns:
            dict: 命令响应消息
        """
        self.logger.info("Processing resume CP command from Central (via Monitor)")

        cp_id = message.get(MessageFields.CP_ID)

        # 验证CP_ID匹配
        if self.engine.cp_id != cp_id:
            self.logger.warning(f"CP_ID不匹配: 期望 {self.engine.cp_id}, 收到 {cp_id}")
            return {
                MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
                MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
                MessageFields.STATUS: ResponseStatus.FAILURE,
                MessageFields.MESSAGE: f"CP_ID mismatch: expected {self.engine.cp_id}, got {cp_id}",
            }

        # 强制清除手动FAULTY模式 - Central的命令优先级最高
        was_faulty = self.engine._manual_faulty_mode
        self.engine._manual_faulty_mode = False

        if was_faulty:
            self.logger.info("✓  Central resume command: Cleared manual FAULTY mode")

        return {
            MessageFields.TYPE: MessageTypes.COMMAND_RESPONSE,
            MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
            MessageFields.STATUS: ResponseStatus.SUCCESS,
            MessageFields.MESSAGE: (
                f"CP {cp_id} resumed, manual FAULTY mode cleared"
                if was_faulty
                else f"CP {cp_id} resumed"
            ),
            MessageFields.CP_ID: cp_id,
        }
