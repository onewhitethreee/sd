"""
Monitor消息分发器

负责处理来自Central和Engine的所有消息，包括：

来自Central的消息：
- register_response: 注册响应
- heartbeat_response: 心跳响应
- start_charging_command: 启动充电会话命令
- stop_charging_session_command: 停止充电会话命令（Driver请求，状态→ACTIVE）
- stop_cp_command: 停止充电点服务命令（管理员命令，状态→STOPPED）
- resume_cp_command: 恢复充电点服务命令（管理员命令，状态→ACTIVE）

来自Engine的消息：
- health_check_response: 健康检查响应
- charging_data: 充电数据（转发到Central）
- charge_completion: 充电完成（转发到Central）
- command_response: 命令执行结果

Monitor作为中间层，主要职责是：
1. 转发Central的命令到Engine
2. 转发Engine的数据到Central
3. 管理充电点状态
"""

import uuid
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Message.MessageTypes import MessageTypes, ResponseStatus, MessageFields


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

        # 来自Central的消息处理器（使用消息类型常量）
        self.central_handlers = {
            MessageTypes.AUTH_RESPONSE: self._handle_auth_response,
            MessageTypes.REGISTER_RESPONSE: self._handle_register_response,
            MessageTypes.HEARTBEAT_RESPONSE: self._handle_heartbeat_response,
            MessageTypes.START_CHARGING_COMMAND: self._handle_start_charging_command,
            MessageTypes.STOP_CHARGING_SESSION_COMMAND: self._handle_stop_charging_session,  # Driver停止充电会话
            MessageTypes.STOP_CP_COMMAND: self._handle_stop_cp_command,  # 管理员停止CP服务
            MessageTypes.RESUME_CP_COMMAND: self._handle_resume_cp_command,
            MessageTypes.STATUS_UPDATE_RESPONSE: self._handle_status_update_response,
            MessageTypes.CHARGING_DATA_RESPONSE: self._handle_charging_data_response,
            MessageTypes.CHARGE_COMPLETION_RESPONSE: self._handle_charging_data_response,
        }

        # 来自Engine的消息处理器（使用消息类型常量）
        self.engine_handlers = {
            MessageTypes.HEALTH_CHECK_RESPONSE: self._handle_health_check_response,
            MessageTypes.CHARGING_DATA: self._handle_charging_data_from_engine,
            MessageTypes.CHARGE_COMPLETION: self._handle_charging_completion_from_engine,
            MessageTypes.COMMAND_RESPONSE: self._handle_command_response,
            MessageTypes.ERROR_RESPONSE: self._handle_error_response,
            MessageTypes.CONNECTION_ERROR: self._handle_error_response,
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
            msg_type = message.get(MessageFields.TYPE)
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
                self.logger.warning(
                    f"Unknown message type from {source}: {msg_type}. "
                    f"Message ID: {message.get(MessageFields.MESSAGE_ID)}"
                )
                return False

        except Exception as e:
            self.logger.error(
                f"Error dispatching message from {source}: {e}. " f"Message: {message}"
            )
            return False

    # ==================== Central消息处理器 ====================

    def _handle_auth_response(self, message):
        """
        处理来自Central的认证响应

        Args:
            message: 认证响应消息，包含：
                - status: "success" 或 "failure" 或 "pending"
                - message: 响应描述
                - cp_id: 充电点ID
        """
        self.logger.debug(f"Received authentication response from Central: {message}")

        status = message.get(MessageFields.STATUS)
        if status == ResponseStatus.SUCCESS:
            self.logger.debug("✓  Authentication successful. Now can register.")
            # 设置授权标志
            self.monitor._authorized = True
            # 认证成功后，自动尝试注册
            # 注意：对于重新连接的充电点，这会更新其注册信息（如价格等）
            self.monitor._register_with_central()
        elif status == "pending":
            # 首次连接，等待管理员批准
            reason = message.get(MessageFields.MESSAGE, "等待管理员批准")
            self.logger.info(f"⏳ Authentication pending: {reason}")
            self.logger.info(
                "Waiting for administrator to authorize this charging point..."
            )
            self.monitor._authorized = False
        else:
            # 认证失败
            reason = message.get(
                MessageFields.REASON, message.get(MessageFields.MESSAGE, "Unknown")
            )
            self.logger.error(f"✗  Authentication failed: {reason}")
            self.logger.info(
                "Waiting for administrator to authorize this charging point..."
            )
            self.monitor._authorized = False

        return True

    def _handle_register_response(self, message):
        """
        处理来自Central的注册响应

        Args:
            message: 注册响应消息，包含：
                - status: "success" 或 "failure"
                - message: 响应描述
                - reason: 失败原因（如果失败）
        """
        self.logger.debug(f"Received registration response from Central: {message}")

        status = message.get(MessageFields.STATUS)
        if status == ResponseStatus.SUCCESS:
            self.logger.debug("Registration successful.")
            # 设置注册确认标志
            self.monitor._registration_confirmed = True

            # 现在才检查是否可以设为 ACTIVE
            if (
                self.monitor.engine_conn_mgr
                and self.monitor.engine_conn_mgr.is_connected
            ):
                self.monitor._check_and_update_to_active()
        else:
            reason = message.get(MessageFields.REASON, "Unknown")
            self.logger.error(f"Registration failed: {reason}")
            self.monitor._registration_confirmed = False

        return True

    def _handle_heartbeat_response(self, message):
        """
        处理来自Central的心跳响应

        Args:
            message: 心跳响应消息，包含：
                - status: "success" 或 "failure" 或 "pending"
        """
        self.logger.debug(f"Received heartbeat response from Central: {message}")

        status = message.get(MessageFields.STATUS)
        info = message.get(MessageFields.MESSAGE, "")

        if status == ResponseStatus.SUCCESS:
            self.logger.debug("Monitor successfully received heartbeat response")
        elif status == "pending":
            # 充电点正在等待授权，这是正常的
            self.logger.debug(f"Heartbeat received, waiting for authorization: {info}")
        else:
            # 只有在status为failure时才警告
            self.logger.warning(
                f"Heartbeat not acknowledged by Central. "
                f"Status field: '{status}' (expected: '{ResponseStatus.SUCCESS}' or 'pending'). "
                f"Full message: {message}"
            )

        return True

    def _handle_start_charging_command(self, message):
        """处理来自Central的启动充电命令"""
        self.logger.debug("Received start charging command from Central.")
        return self.monitor._handle_start_charging_command(message)

    def _handle_stop_charging_session(self, message):
        """
        处理来自Central的停止充电会话命令（Driver请求停止充电）

        Args:
            message: 停止充电会话命令，包含：
                - cp_id: 充电点ID
                - session_id: 会话ID
                - driver_id: Driver ID

        重要：Monitor在转发停止命令后应立即更新状态为ACTIVE，
        表示充电会话已结束，充电桩恢复到可用状态。
        """
        self.logger.debug("Received stop charging session command from Central (Driver request).")

        cp_id = message.get(MessageFields.CP_ID)
        session_id = message.get(MessageFields.SESSION_ID)

        # 向Engine发送停止充电命令（使用常量）
        stop_message = {
            MessageFields.TYPE: MessageTypes.STOP_CHARGING_COMMAND,
            MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
            MessageFields.CP_ID: cp_id,
            MessageFields.SESSION_ID: session_id,
        }

        if self.monitor.engine_conn_mgr and self.monitor.engine_conn_mgr.is_connected:
            self.monitor.engine_conn_mgr.send(stop_message)
            self.logger.info(
                f"Stop charging command forwarded to Engine: CP {cp_id}, Session {session_id}"
            )
            # ✓  立即更新Monitor状态为ACTIVE（停止充电，恢复可用状态）
            # 注意：如果Engine或Central断开连接，update_cp_status会自动处理为FAULTY状态
            from Common.Config.Status import Status

            self.monitor.update_cp_status(Status.ACTIVE.value)
            # 清除充电数据（充电停止）
            self.monitor._current_charging_data = None
            self.logger.info(
                f"Monitor status updated to ACTIVE after stop charging for session {session_id}"
            )
            return True
        else:
            self.logger.error("Engine connection unavailable, cannot forward stop charging command")
            return False

    def _handle_stop_cp_command(self, message):
        """
        处理来自Central的停止充电点命令（管理员命令）

        这是管理员使用stop命令暂停充电点服务，与停止充电会话不同。
        充电点进入STOPPED状态后不再接受新的充电请求。

        Args:
            message: 停止充电点命令，包含：
                - cp_id: 充电点ID
        """
        self.logger.debug("Received stop CP command from Central (admin command).")

        cp_id = message.get(MessageFields.CP_ID)

        # 向Engine发送停止命令（如果有正在进行的充电会话，需要先停止）
        # 使用session_id=None表示强制停止任何活跃会话
        stop_message = {
            MessageFields.TYPE: MessageTypes.STOP_CHARGING_COMMAND,
            MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
            MessageFields.CP_ID: cp_id,
            MessageFields.SESSION_ID: None,  # None表示强制停止
        }

        if self.monitor.engine_conn_mgr and self.monitor.engine_conn_mgr.is_connected:
            self.monitor.engine_conn_mgr.send(stop_message)
            self.logger.info(f"Stop CP command forwarded to Engine: CP {cp_id}")

            # 更新Monitor状态为STOPPED（充电点暂停服务）
            from Common.Config.Status import Status

            self.monitor.update_cp_status(Status.STOPPED.value)
            self.logger.info(
                f"Monitor status updated to STOPPED (admin stop command)"
            )
            return True
        else:
            self.logger.error("Engine connection unavailable, cannot forward stop CP command")
            return False

    def _handle_resume_cp_command(self, message):
        """
        处理来自Central的恢复充电点命令

        当Central管理员使用resume命令时，这个命令会强制Engine退出手动FAULTY模式，
        覆盖Engine CLI的手动设置。Central的命令优先级更高。

        Args:
            message: 恢复命令，包含：
                - cp_id: 充电点ID
        """
        self.logger.debug("Received resume CP command from Central.")

        cp_id = message.get(MessageFields.CP_ID)

        # 向Engine发送恢复命令（使用特殊的消息类型）
        # Engine需要识别这是来自Central的强制恢复命令
        resume_message = {
            MessageFields.TYPE: MessageTypes.RESUME_CP_COMMAND,
            MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
            MessageFields.CP_ID: cp_id,
        }

        if self.monitor.engine_conn_mgr and self.monitor.engine_conn_mgr.is_connected:
            self.monitor.engine_conn_mgr.send(resume_message)
            self.logger.info(f"Resume command forwarded to Engine: CP {cp_id}")

            # Monitor立即更新状态为ACTIVE（如果Engine和Central都连接正常）
            if (
                self.monitor.central_conn_mgr
                and self.monitor.central_conn_mgr.is_connected
            ):
                self.monitor.update_cp_status("ACTIVE")
                self.logger.info(f"Monitor status updated to ACTIVE (Central resume command)")

            return True
        else:
            self.logger.error("Engine connection unavailable, cannot forward resume command")
            return False

    def _handle_status_update_response(self, message):
        """
        处理来自Central的状态更新响应

        Args:
            message: 状态更新响应消息，包含：
                - status: "success" 或 "failure"
                - message: 响应描述
                - reason: 失败原因（如果失败）
        """
        self.logger.debug(f"Received status update response from Central: {message}")
        return True

    def _handle_charging_data_response(self, message):
        """
        处理来自Central的充电数据响应

        Args:
            message: 充电数据响应消息，包含：
                - status: "success" 或 "failure"
                - message: 响应描述
                - reason: 失败原因（如果失败）
                - charging_data: 充电数据
        """
        self.logger.debug(f"Received charging data response from Central: {message}")
        return True

    # ==================== Engine消息处理器 ====================

    def _handle_health_check_response(self, message):
        """
        处理来自Engine的健康检查响应

        根据规范：
        - Monitor_OK and Engine_OK => Activado (Verde)
        - Monitor_OK and Engine_KO => Averiado (Rojo)

        Args:
            message: 健康检查响应，包含：
                - status: 响应状态
                - engine_status: Engine当前状态
                - is_charging: 是否正在充电
        """
        self.logger.debug(f"Health check response from Engine: {message}")

        # 更新最后一次收到健康检查响应的时间
        # 这是防止健康检查超时的关键
        self.monitor._update_last_health_response()

        engine_status = message.get(MessageFields.ENGINE_STATUS)

        # Monitor está OK (recibiendo health check), verificar estado de Engine
        if engine_status == "FAULTY":
            # Monitor OK + Engine KO = FAULTY
            self.logger.warning("Engine reports FAULTY status.")
            self.monitor.update_cp_status("FAULTY")
        elif engine_status == "CHARGING":
            # Engine está cargando - esto es normal y significa que está funcionando bien
            self.logger.debug("Engine reports CHARGING status.")
            # Si está cargando, el CP debe estar en estado CHARGING
            if (
                self.monitor.central_conn_mgr
                and self.monitor.central_conn_mgr.is_connected
            ):
                self.monitor.update_cp_status("CHARGING")
            else:
                # Si Central desconectado mientras carga, poner en FAULTY
                self.logger.warning("Engine is CHARGING but Central is not connected")
                self.monitor.update_cp_status("FAULTY")
        elif engine_status == "ACTIVE":
            self.logger.debug("Engine reports ACTIVE status.")
            # Monitor OK + Engine OK = ACTIVE (solo si Central también conectado)
            if (
                self.monitor.central_conn_mgr
                and self.monitor.central_conn_mgr.is_connected
            ):
                # 使用统一的检查方法，避免重复状态更新
                self.monitor._check_and_update_to_active()
            else:
                # Monitor OK, Engine OK, pero Central desconectado
                self.logger.warning("Engine is ACTIVE but Central is not connected")
                self.monitor.update_cp_status("FAULTY")
        else:
            self.logger.error(f"Unknown engine status received: {engine_status}")
            self.monitor.update_cp_status("FAULTY")
        return True

    def _handle_charging_data_from_engine(self, message):
        """处理来自Engine的充电数据"""
        self.logger.debug("Received charging data from Engine.")
        return self.monitor._handle_charging_data_from_engine(message)

    def _handle_charging_completion_from_engine(self, message):
        """处理来自Engine的充电完成通知"""
        self.logger.debug("Received charging completion from Engine.")
        return self.monitor._handle_charging_completion_from_engine(message)

    def _handle_command_response(self, message):
        """
        处理来自Engine的命令响应

        Engine在处理start_charging_command或stop_charging_command后会返回此响应。
        这个响应通过MySocketServer的自动响应机制发送，包含命令执行的结果。

        虽然当前只记录日志，但保留此处理器可以：
        1. 消除"Unknown message type"的warning日志
        2. 便于未来添加命令执行验证逻辑（如重试机制）
        3. 保持消息流的完整性和可追踪性

        Args:
            message: 命令响应消息，包含：
                - type: "command_response"
                - message_id: 对应的命令message_id
                - status: "success" 或 "failure"
                - message: 执行结果描述
                - session_id: 会话ID（如果适用）

        Returns:
            bool: 总是返回True表示消息已处理
        """
        status = message.get(MessageFields.STATUS)
        msg = message.get(MessageFields.MESSAGE, "")
        session_id = message.get(MessageFields.SESSION_ID)

        if status == ResponseStatus.SUCCESS:
            self.logger.debug(
                f"Engine命令执行成功: {msg}"
                + (f" (session: {session_id})" if session_id else "")
            )
        elif status == ResponseStatus.FAILURE:
            self.logger.warning(
                f"Engine命令执行失败: {msg}"
                + (f" (session: {session_id})" if session_id else "")
            )
        else:
            self.logger.error(f"Engine returned unknown status: {status}, message: {msg}")

        return True

    def _handle_error_response(self, message):
        """
        处理来自Engine的错误响应

        Args:
            message: 错误响应消息，包含：
                - type: "error_response"
                - message_id: 对应的请求message_id
                - error_code: 错误代码
                - message: 错误描述

        Returns:
            bool: 总是返回True表示消息已处理
        """
        error_code = message.get("error_code", "Unknown")
        error_msg = message.get(MessageFields.MESSAGE, "")

        self.logger.error(
            f"Received error response from Engine: "
            f"Error Code: {error_code}, Message: {error_msg}"
        )

        return True
