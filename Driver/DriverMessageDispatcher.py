"""
Driver消息分发器
负责处理来自Central的所有消息，包括：
- charge_request_response: 充电请求响应
- charging_status_update: 充电状态更新
- charge_completion_notification: 充电完成通知
- available_cps_response: 可用充电点列表
- charging_data: 实时充电数据
- CONNECTION_LOST: 连接丢失
- CONNECTION_ERROR: 连接错误
"""

import time
from datetime import datetime


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

        # 来自Central的消息处理器
        self.handlers = {
            "charge_request_response": self._handle_charge_response,
            "charging_status_update": self._handle_charging_status,
            "charge_completion_notification": self._handle_charge_completion,
            "charge_completion": self._handle_charge_completion,
            "available_cps_response": self._handle_available_cps,
            "charging_data": self._handle_charging_data,
            "CONNECTION_LOST": self._handle_connection_lost,
            "CONNECTION_ERROR": self._handle_connection_error,
            "stop_charging_response": self._handle_stop_charging_response,
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
            msg_type = message.get("type")
            self.logger.debug(f"Dispatching message type: {msg_type}")

            handler = self.handlers.get(msg_type)
            if handler:
                return handler(message)
            else:
                self.logger.warning(f"Unknown message type from Central: {msg_type}")
                return False

        except Exception as e:
            self.logger.error(f"Error dispatching message: {e}", exc_info=True)
            return False

    # ==================== 消息处理器 ====================

    def _handle_charge_response(self, message):
        """处理充电请求响应"""
        status = message.get("status")
        info = message.get("info", "")
        self.logger.debug(f"处理充电请求响应: status={status}, info={info}")
        self.logger.debug(f"message: {message}")
        if status == "success":
            self.logger.info(f"✅ Charging request approved: {info}")
            session_id = message.get("session_id")
            cp_id = message.get("cp_id")

            if session_id:
                with self.driver.lock:
                    self.driver.current_charging_session = {
                        "session_id": session_id,
                        "cp_id": cp_id,
                        "start_time": datetime.now(),
                        "status": "authorized",
                        "energy_consumed_kwh": 0.0,
                        "total_cost": 0.0,
                        "charging_rate": 0.0,
                    }
                self.logger.info(f"✅ Charging session created: {session_id}")
                self.logger.debug(f"会话数据: {self.driver.current_charging_session}")
            else:
                self.logger.error("Session ID not provided in charge response")
        else:
            self.logger.error(f"❌ Charging request denied: {info}")

        return True

    def _handle_charging_status(self, message):
        """处理充电状态更新"""

        session_id = message.get("session_id")
        energy_consumed_kwh = message.get("energy_consumed_kwh", 0)
        total_cost = message.get("total_cost", 0)
        charging_rate = message.get("charging_rate", 0)

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
                    self.driver.current_charging_session["charging_rate"] = (
                        charging_rate
                    )

                    self.logger.info(
                        f"🔋 Charging progress - Energy: {energy_consumed_kwh:.3f}kWh, Cost: €{total_cost:.2f}, Rate: {charging_rate:.2f}kW"
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
        """处理实时充电数据（来自Engine通过Monitor转发）"""
        session_id = message.get("session_id")
        with self.driver.lock:
            if (
                self.driver.current_charging_session
                and self.driver.current_charging_session.get("session_id") == session_id
            ):
                energy_consumed_kwh = message.get("energy_consumed_kwh", 0)
                total_cost = message.get("total_cost", 0)
                charging_rate = message.get("charging_rate", 0)

                self.driver.current_charging_session["energy_consumed_kwh"] = (
                    energy_consumed_kwh
                )
                self.driver.current_charging_session["total_cost"] = total_cost
                self.driver.current_charging_session["charging_rate"] = charging_rate

                self.logger.info(
                    f"🔋 Real-time charging data - Energy: {energy_consumed_kwh:.3f}kWh, Cost: €{total_cost:.2f}, Rate: {charging_rate:.2f}kW"
                )

        return True

    def _handle_charge_completion(self, message):
        """处理充电完成通知"""
        with self.driver.lock:
            if self.driver.current_charging_session:
                session_id = message.get("session_id")
                energy_consumed_kwh = message.get("energy_consumed_kwh", 0)
                total_cost = message.get("total_cost", 0)

                self.logger.info(f"✅ Charging completed!")
                self.logger.info(f"Session ID: {session_id}")
                self.logger.info(f"Total Energy: {energy_consumed_kwh:.3f}kWh")
                self.logger.info(f"Total Cost: €{total_cost:.2f}")

                # 保存到历史记录
                completion_record = {
                    "session_id": session_id,
                    "cp_id": self.driver.current_charging_session.get("cp_id"),
                    "completion_time": datetime.now(),
                    "energy_consumed_kwh": energy_consumed_kwh,
                    "total_cost": total_cost,
                }
                self.driver.charging_history.append(completion_record)

                self.driver.current_charging_session = None

        # 等待4秒后处理下一个服务
        self.logger.info("Waiting 4 seconds before next service...")
        time.sleep(4)
        self.driver._process_next_service()

        return True

    def _handle_available_cps(self, message):
        """处理可用充电点列表"""
        self.driver.available_charging_points = message.get("charging_points", [])
        self.logger.info(
            f"Available charging points: {len(self.driver.available_charging_points)}"
        )

        self.driver._formatter_charging_points(self.driver.available_charging_points)

        return True

    def _handle_connection_lost(self, message):
        """处理连接丢失"""
        self.logger.warning("Connection to Central lost")
        self.driver._handle_connection_lost()
        return True

    def _handle_connection_error(self, message):
        """处理连接错误"""
        error = message.get("error", "Unknown error")
        self.logger.error(f"Connection error: {error}")
        self.driver._handle_connection_error(message)
        return True

    def _handle_stop_charging_response(self, message):
        """处理停止充电响应"""
        self.logger.info("Charging stopped")
        self.logger.debug(f"处理停止充电响应: {message}")
        return True
