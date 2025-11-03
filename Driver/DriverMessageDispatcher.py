"""
Driver消息分发器

负责处理来自Central的所有消息，包括：

来自 Central 的响应和通知：
- charge_request_response: 充电请求响应
- stop_charging_response: 停止充电响应
- available_cps_response: 可用充电点列表
- charging_status_update: 充电状态更新
- charging_data: 实时充电数据（来自Engine）
- charge_completion: 充电完成通知

系统事件：
- CONNECTION_LOST: 连接丢失
- CONNECTION_ERROR: 连接错误

Driver作为用户端，主要职责是：
1. 接收充电请求的响应
2. 实时显示充电进度
3. 处理充电完成并保存历史
4. 管理连接状态
"""

import time
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Common.Message.MessageTypes import MessageTypes, ResponseStatus, MessageFields


class DriverMessageDispatcher:
    """
    Driver消息分发器
    统一处理来自Central的消息，提供清晰的消息处理接口
    """

    def __init__(self, logger, driver):
        """
        初始化DriverMessageDispatcher

        Args:
            logger: 日志记录器
            driver: Driver实例，用于访问Driver的业务逻辑
        """
        self.logger = logger
        self.driver = driver

        # 来自Central的消息处理器（使用消息类型常量）
        self.handlers = {
            # 响应消息
            MessageTypes.CHARGE_REQUEST_RESPONSE: self._handle_charge_response,
            MessageTypes.STOP_CHARGING_RESPONSE: self._handle_stop_charging_response,
            MessageTypes.AVAILABLE_CPS_RESPONSE: self._handle_available_cps,
            MessageTypes.CHARGING_HISTORY_RESPONSE: self._handle_charging_history_response,

            # 通知消息
            MessageTypes.CHARGING_STATUS_UPDATE: self._handle_charging_status,
            MessageTypes.CHARGING_DATA: self._handle_charging_data,
            MessageTypes.CHARGE_COMPLETION: self._handle_charge_completion,

            # 系统事件
            MessageTypes.CONNECTION_LOST: self._handle_connection_lost,
            MessageTypes.CONNECTION_ERROR: self._handle_connection_error,
        }

    def dispatch_message(self, message):
        """
        分发消息到对应的处理器

        Args:
            message: 消息字典

        Returns:
            bool: 处理是否成功
        """
        try:
            msg_type = message.get(MessageFields.TYPE)
            self.logger.debug(f"Dispatching message type: {msg_type}")

            handler = self.handlers.get(msg_type)
            if handler:
                return handler(message)
            else:
                self.logger.warning(
                    f"Unknown message type from Central: {msg_type}. "
                    f"Message ID: {message.get(MessageFields.MESSAGE_ID)}"
                )
                return False

        except Exception as e:
            self.logger.error(
                f"Error dispatching message {message.get(MessageFields.TYPE)}: {e}. "
                f"Message: {message}",
                exc_info=True
            )
            return False

    # ==================== 消息处理器 ====================

    def _handle_charge_response(self, message):
        """
        处理充电请求响应

        Args:
            message: 响应消息，包含：
                - status: "success" 或 "failure"
                - message/info: 响应描述
                - session_id: 会话ID（成功时）
                - cp_id: 充电点ID（成功时）
        """
        status = message.get(MessageFields.STATUS)
        info = message.get("info", message.get(MessageFields.MESSAGE, ""))
        self.logger.debug(f"处理充电请求响应: status={status}, info={info}")
        self.logger.debug(f"message: {message}")

        if status == ResponseStatus.SUCCESS:
            self.logger.info(f"✅ Charging request approved: {info}")
            session_id = message.get(MessageFields.SESSION_ID)
            cp_id = message.get(MessageFields.CP_ID)

            if session_id:
                with self.driver.lock:
                    self.driver.current_charging_session = {
                        "session_id": session_id,
                        "cp_id": cp_id,
                        "start_time": time.time(),  # 使用Unix时间戳而不是datetime对象
                        "status": "authorized",
                        "energy_consumed_kwh": 0.0,
                        "total_cost": 0.0,
                    }
                self.logger.info(f"✅ Charging session created: {session_id}")
                self.logger.debug(f"会话数据: {self.driver.current_charging_session}")
            else:
                self.logger.error("Session ID not provided in charge response")
        else:
            self.logger.error(f"❌ Charging request denied: {info}")

        return True

    def _handle_charging_status(self, message):
        """
        处理充电状态更新

        Args:
            message: 状态更新消息，包含：
                - session_id: 会话ID
                - energy_consumed_kwh: 已消耗电量
                - total_cost: 总费用
        """
        session_id = message.get(MessageFields.SESSION_ID)
        energy_consumed_kwh = message.get(MessageFields.ENERGY_CONSUMED_KWH, 0)
        total_cost = message.get(MessageFields.TOTAL_COST, 0)

        with self.driver.lock:
            if self.driver.current_charging_session:
                current_session_id = self.driver.current_charging_session.get(
                    "session_id"
                )
                # 验证会话ID匹配
                if current_session_id == session_id:
                    # 更新会话数据
                    self.driver.current_charging_session["energy_consumed_kwh"] = (
                        energy_consumed_kwh
                    )
                    self.driver.current_charging_session["total_cost"] = total_cost

                    # Usar DEBUG para no interrumpir input del usuario en modo interactivo
                    self.logger.debug(
                        f"🔋 Charging progress - Energy: {energy_consumed_kwh:.3f}kWh, Cost: €{total_cost:.2f}kW"
                    )
                else:
                    self.logger.warning(
                        f"会话ID不匹配: 期望 {current_session_id}, 收到 {session_id}"
                    )
            else:
                self.logger.warning(
                    f"没有活跃的充电会话，无法更新状态。收到的会话ID: {session_id}"
                )

        return True

    def _handle_charging_data(self, message):
        """
        处理实时充电数据（来自Engine通过Monitor和Central转发）

        Args:
            message: 充电数据消息，包含：
                - session_id: 会话ID
                - energy_consumed_kwh: 已消耗电量
                - total_cost: 总费用
        """
        session_id = message.get(MessageFields.SESSION_ID)
        with self.driver.lock:
            if (
                self.driver.current_charging_session
                and self.driver.current_charging_session.get("session_id") == session_id
            ):
                energy_consumed_kwh = message.get(MessageFields.ENERGY_CONSUMED_KWH, 0)
                total_cost = message.get(MessageFields.TOTAL_COST, 0)

                self.driver.current_charging_session["energy_consumed_kwh"] = (
                    energy_consumed_kwh
                )
                self.driver.current_charging_session["total_cost"] = total_cost

                # Usar DEBUG para no interrumpir input del usuario en modo interactivo
                self.logger.debug(
                    f"🔋 Real-time charging data - Energy: {energy_consumed_kwh:.3f}kWh, Cost: €{total_cost:.2f}"
                )

        return True

    def _handle_charge_completion(self, message):
        """
        处理充电完成通知

        Args:
            message: 完成通知消息，包含：
                - session_id: 会话ID
                - energy_consumed_kwh: 总消耗电量
                - total_cost: 总费用
        """
        with self.driver.lock:
            if self.driver.current_charging_session:
                session_id = message.get(MessageFields.SESSION_ID)
                energy_consumed_kwh = message.get(MessageFields.ENERGY_CONSUMED_KWH, 0)
                total_cost = message.get(MessageFields.TOTAL_COST, 0)

                self.logger.info(f"✅ Charging completed!")
                self.logger.info(f"Session ID: {session_id}")
                self.logger.info(f"Total Energy: {energy_consumed_kwh:.3f}kWh")
                self.logger.info(f"Total Cost: €{total_cost:.2f}")

                # ✅ 不再保存到内存：历史记录已经在 Central 的数据库中
                # 充电完成后，数据已经持久化在 Central，Driver 可以通过查询 API 获取

                self.driver.current_charging_session = None

        # 等待4秒后处理下一个服务
        self.logger.info("Waiting 4 seconds before next service...")
        time.sleep(4)
        self.driver._process_next_service()

        return True

    def _handle_available_cps(self, message):
        """
        处理可用充电点列表

        Args:
            message: 列表消息，包含：
                - charging_points: 充电点列表
        """
        import time
        self.driver.available_charging_points = message.get(MessageFields.CHARGING_POINTS, [])
        self.driver.available_cps_cache_time = time.time()  # 更新缓存时间

        self.logger.info(
            f"Available charging points: {len(self.driver.available_charging_points)}"
        )

        self.driver._formatter_charging_points(self.driver.available_charging_points)

        return True

    def _handle_charging_history_response(self, message):
        """
        处理充电历史查询响应（CQRS Query Response）

        这是对 charging_history_request 的响应，包含从数据库查询的历史记录。

        Args:
            message: 历史记录响应，包含：
                - status: 响应状态
                - history: 历史记录列表
                - count: 记录数量
        """
        status = message.get(MessageFields.STATUS)

        if status == "success":
            history = message.get("history", [])
            count = message.get("count", 0)

            self.logger.info(f"✅ Received {count} charging history records from Central")

            # 调用 Driver 的显示方法（传入查询到的数据）
            self.driver._show_charging_history(history)
        else:
            error = message.get("error", "Unknown error")
            self.logger.error(f"❌ Failed to retrieve charging history: {error}")

        return True

    def _handle_connection_lost(self, message):
        """处理连接丢失"""
        self.logger.warning(f"Connection to Central lost: {message}")
        self.driver._handle_connection_lost()
        return True

    def _handle_connection_error(self, message):
        """处理连接错误"""
        error = message.get("error", "Unknown error")
        self.logger.error(f"Connection error: {error}")
        self.driver._handle_connection_error(message)
        return True

    def _handle_stop_charging_response(self, message):
        """
        处理停止充电响应

        Args:
            message: 响应消息，包含：
                - status: 响应状态 (success/failure)
                - message/info: 响应信息
                - session_id: 会话ID
                - cp_id: 充电点ID

        Returns:
            bool: 处理是否成功
        """
        status = message.get(MessageFields.STATUS)
        info = message.get("info", message.get(MessageFields.MESSAGE, ""))
        session_id = message.get(MessageFields.SESSION_ID)
        cp_id = message.get(MessageFields.CP_ID)

        self.logger.debug(f"处理停止充电响应: status={status}, info={info}")

        if status == ResponseStatus.SUCCESS:
            self.logger.info(f"🛑 Stop charging request accepted for session {session_id}")
            self.logger.info(f"   Charging point: {cp_id}")
            self.logger.info(f"   Waiting for final charge completion notification...")

            # 注意：不要在这里清理 current_charging_session
            # charge_completion 消息会随后到达并完成会话清理和历史记录保存

        else:
            self.logger.error(f"❌ Failed to stop charging: {info}")
            self.logger.error(f"   Session ID: {session_id}")

            # 如果停止失败，可能是会话已经不存在或其他错误
            # 建议检查本地会话状态
            with self.driver.lock:
                if self.driver.current_charging_session:
                    local_session_id = self.driver.current_charging_session.get("session_id")
                    if local_session_id != session_id:
                        self.logger.warning(
                            f"   Local session ID ({local_session_id}) differs from requested ({session_id})"
                        )

        return True
