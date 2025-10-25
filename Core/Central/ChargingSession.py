"""
专门管理充电会话 (charging sessions)。
创建、更新、查询会话，处理计费逻辑。
同样，相关的数据库操作（db_manager.create_charging_session、update_charging_session 等）应该移到这里。
"""

import os
import sys
import uuid
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Database.SqliteConnection import SqliteConnection


class ChargingSession:
    """
    充电会话管理类，负责充电会话的生命周期管理和计费逻辑。
    """

    def __init__(self, logger, db_manager):
        """
        初始化ChargingSession管理器

        Args:
            logger: 日志记录器
            db_manager: 数据库管理器
        """
        self.logger = logger
        self.db_manager: SqliteConnection = db_manager
        # 内存中的充电会话映射：{session_id: session_info}
        self._charging_sessions = {}

    def create_charging_session(self, cp_id, driver_id):
        """
        创建一个新的充电会话

        Args:
            cp_id: 充电桩ID
            driver_id: 司机ID

        Returns:
            tuple: (session_id: str or None, error_message: str or None)
        """
        try:
            session_id = str(uuid.uuid4())
            start_time = datetime.now().isoformat()

            # 确保充电桩存在于数据库（外键约束）
            if not self.db_manager.charging_point_exists(cp_id):
                self.logger.warning(f"充电桩 {cp_id} 不存在于数据库，创建默认记录...")
                # 创建一个默认的充电桩记录
                if not self.db_manager.insert_or_update_charging_point(
                    cp_id=cp_id,
                    location="Unknown",
                    price_per_kwh=0.0,
                    status="DISCONNECTED",
                    last_connection_time=None,
                ):
                    raise Exception(f"无法为充电桩 {cp_id} 创建数据库记录")

            # 注册司机（如果尚未注册）
            if not self.db_manager.register_driver(driver_id, f"driver_{driver_id}"):
                raise Exception(f"无法注册司机 {driver_id}")

            # 创建充电会话
            if not self.db_manager.create_charging_session(
                session_id, cp_id, driver_id, start_time
            ):
                raise Exception("创建充电会话失败")

            # 保存到内存
            self._charging_sessions[session_id] = {
                "session_id": session_id,
                "cp_id": cp_id,
                "driver_id": driver_id,
                "start_time": start_time,
                "end_time": None,
                "energy_consumed_kwh": 0.0,
                "total_cost": 0.0,
                "status": "in_progress",
            }

            self.logger.info(f"充电会话 {session_id} 创建成功")
            return session_id, None

        except Exception as e:
            self.logger.error(f"创建充电会话失败: {e}")
            return None, str(e)

    def update_charging_session(
        self, session_id, energy_consumed_kwh, total_cost, status="in_progress"
    ):
        """
        更新充电会话数据

        Args:
            session_id: 会话ID
            energy_consumed_kwh: 消耗的电量（kWh）
            total_cost: 总费用
            status: 会话状态

        Returns:
            bool: 是否成功
        """
        try:
            # Check if session exists in memory, if not try to load from database
            if session_id not in self._charging_sessions:
                db_session = self.db_manager.get_charging_session(session_id)
                if not db_session:
                    self.logger.warning(f"充电会话 {session_id} 不存在")
                    return False
                # Load into memory cache
                self._charging_sessions[session_id] = db_session

            # 更新数据库
            self.db_manager.update_charging_session(
                session_id=session_id,
                energy_consumed_kwh=energy_consumed_kwh,
                total_cost=total_cost,
                status=status,
            )

            # 更新内存
            self._charging_sessions[session_id][
                "energy_consumed_kwh"
            ] = energy_consumed_kwh
            self._charging_sessions[session_id]["total_cost"] = total_cost
            self._charging_sessions[session_id]["status"] = status

            self.logger.debug(
                f"会话 {session_id} 已更新: 电量={energy_consumed_kwh}kWh, 费用=€{total_cost}"
            )
            return True

        except Exception as e:
            self.logger.error(f"更新充电会话 {session_id} 失败: {e}")
            return False

    def complete_charging_session(self, session_id, energy_consumed_kwh, total_cost):
        """
        完成充电会话

        Args:
            session_id: 会话ID
            energy_consumed_kwh: 消耗的电量（kWh）
            total_cost: 总费用

        Returns:
            tuple: (success: bool, session_data: dict or None)
        """
        try:
            # Check if session exists in memory, if not try to load from database
            if session_id not in self._charging_sessions:
                db_session = self.db_manager.get_charging_session(session_id)
                if not db_session:
                    self.logger.warning(f"充电会话 {session_id} 不存在")
                    return False, None
                # Load into memory cache
                self._charging_sessions[session_id] = db_session

            end_time = datetime.now().isoformat()

            # 更新数据库
            self.db_manager.update_charging_session(
                session_id=session_id,
                end_time=end_time,
                energy_consumed_kwh=energy_consumed_kwh,
                total_cost=total_cost,
                status="completed",
            )

            # 更新内存
            session_data = self._charging_sessions[session_id].copy()
            session_data["end_time"] = end_time
            session_data["energy_consumed_kwh"] = energy_consumed_kwh
            session_data["total_cost"] = total_cost
            session_data["status"] = "completed"

            self._charging_sessions[session_id] = session_data

            self.logger.info(
                f"充电会话 {session_id} 已完成: 电量={energy_consumed_kwh}kWh, 费用=€{total_cost}"
            )
            return True, session_data

        except Exception as e:
            self.logger.error(f"完成充电会话 {session_id} 失败: {e}")
            return False, None

    def get_charging_session(self, session_id):
        """
        获取充电会话信息

        Args:
            session_id: 会话ID

        Returns:
            dict: 会话信息或None
        """
        # First check in-memory cache
        session = self._charging_sessions.get(session_id)
        if session:
            return session

        # If not in memory, try to load from database
        # This handles cases where the session was created but not yet in memory
        # or if the Central process was restarted
        try:
            db_session = self.db_manager.get_charging_session(session_id)
            if db_session:
                # Load into memory cache for future access
                self._charging_sessions[session_id] = db_session
                self.logger.debug(
                    f"Loaded charging session {session_id} from database into memory cache"
                )
                return db_session
        except Exception as e:
            self.logger.warning(
                f"Failed to load charging session {session_id} from database: {e}"
            )

        return None

    def is_session_active(self, session_id):
        """
        检查会话是否活跃

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否活跃
        """
        session = self._charging_sessions.get(session_id)
        return session is not None and session["status"] == "in_progress"

    def get_active_sessions_for_charging_point(self, cp_id):
        """
        获取充电桩的所有活跃会话

        Args:
            cp_id: 充电桩ID

        Returns:
            list: 活跃会话列表
        """
        return [
            session
            for session in self._charging_sessions.values()
            if session["cp_id"] == cp_id and session["status"] == "in_progress"
        ]

    def get_active_sessions_for_driver(self, driver_id):
        """
        获取司机的所有活跃会话

        Args:
            driver_id: 司机ID

        Returns:
            list: 活跃会话列表
        """
        return [
            session
            for session in self._charging_sessions.values()
            if session["driver_id"] == driver_id and session["status"] == "in_progress"
        ]

    def get_all_charging_sessions(self):
        """
        获取所有充电会话

        Returns:
            list: 所有会话列表
        """
        return list(self._charging_sessions.values())

# TODO 不需要保存到内存，只需要随时的从数据库中读取