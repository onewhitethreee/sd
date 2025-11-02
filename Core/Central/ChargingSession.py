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
from Common.Config.Status import Status
from Common.Database.SqliteConnection import SqliteConnection
from Common.Database.ChargingSessionRepository import ChargingSessionRepository
from Common.Database.ChargingPointRepository import ChargingPointRepository
from Common.Database.DriverRepository import DriverRepository


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
        # 使用Repository进行数据库操作
        self.repository = ChargingSessionRepository(db_manager)
        self.cp_repository = ChargingPointRepository(db_manager)
        self.driver_repository = DriverRepository(db_manager)

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

            # 确保充电桩存在于数据库（使用Repository）
            if not self.cp_repository.exists(cp_id):
                self.logger.warning(f"充电桩 {cp_id} 不存在于数据库，创建默认记录...")
                # 创建一个默认的充电桩记录
                if not self.cp_repository.insert_or_update(
                    cp_id=cp_id,
                    location="Unknown",
                    price_per_kwh=0.0,
                    status="DISCONNECTED",
                    last_connection_time=None,
                ):
                    raise Exception(f"无法为充电桩 {cp_id} 创建数据库记录")

            # 注册司机（如果尚未注册，使用Repository）
            if not self.driver_repository.exists(driver_id):
                if not self.driver_repository.register(driver_id, f"driver_{driver_id}"):
                    raise Exception(f"无法注册司机 {driver_id}")

            # 创建充电会话（使用Repository）
            if not self.repository.create(session_id, cp_id, driver_id, start_time):
                raise Exception("创建充电会话失败")

            self.logger.info(f"充电会话 {session_id} 创建成功")
            return session_id, None

        except Exception as e:
            self.logger.error(f"创建充电会话失败: {e}")
            return None, str(e)

    def update_charging_session(
        self, session_id, energy_consumed_kwh, total_cost, status=Status.CHARGING.value
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
            # 检查会话是否存在（使用Repository）
            db_session = self.repository.get_by_id(session_id)
            if not db_session:
                self.logger.warning(f"充电会话 {session_id} 不存在")
                return False

            # 更新数据库（使用Repository）
            self.repository.update(
                session_id=session_id,
                energy_consumed_kwh=energy_consumed_kwh,
                total_cost=total_cost,
                status=status,
            )

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
            # 检查会话是否存在（使用Repository）
            db_session = self.repository.get_by_id(session_id)
            if not db_session:
                self.logger.warning(f"充电会话 {session_id} 不存在")
                return False, None

            end_time = datetime.now().isoformat()

            # 更新数据库（使用Repository）
            self.repository.update(
                session_id=session_id,
                end_time=end_time,
                energy_consumed_kwh=energy_consumed_kwh,
                total_cost=total_cost,
                status="completed",
            )

            # 从数据库获取更新后的会话数据
            session_data = self.repository.get_by_id(session_id)

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
        try:
            return self.repository.get_by_id(session_id)
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
        return self.repository.is_active(session_id)

    def get_active_sessions_for_charging_point(self, cp_id):
        """
        获取充电桩的所有活跃会话

        Args:
            cp_id: 充电桩ID

        Returns:
            list: 活跃会话列表
        """
        return self.repository.get_active_sessions_by_charging_point(cp_id)

    def get_active_sessions_for_driver(self, driver_id):
        """
        获取司机的所有活跃会话

        Args:
            driver_id: 司机ID

        Returns:
            list: 活跃会话列表
        """
        return self.repository.get_active_sessions_by_driver(driver_id)

    def get_all_charging_sessions(self):
        """
        获取所有充电会话

        Returns:
            list: 所有会话列表
        """
        return self.repository.get_active_sessions()

    def get_all_sessions(self):
        """
        获取所有充电会话（包括历史会话）

        Returns:
            list: 所有会话列表
        """
        try:
            return self.repository.get_all()
        except Exception as e:
            self.logger.error(f"获取所有会话失败: {e}")
            return []

    def get_session(self, session_id):
        """
        获取指定的充电会话信息（别名方法）

        Args:
            session_id: 会话ID

        Returns:
            dict: 会话信息或None
        """
        return self.get_charging_session(session_id)

    def get_driver_charging_history(self, driver_id, limit=None):
        """
        获取司机的充电历史记录（包括所有已完成的会话）

        Args:
            driver_id: 司机ID
            limit: 可选，限制返回的记录数量

        Returns:
            list: 充电历史记录列表，按时间倒序排列
        """
        try:
            sessions = self.repository.get_sessions_by_driver(driver_id)

            # 只返回已完成的会话（status = "completed"）
            completed_sessions = [s for s in sessions if s.get("status") == "completed"]

            # 如果指定了limit，限制返回数量
            if limit:
                completed_sessions = completed_sessions[:limit]

            self.logger.info(f"Retrieved {len(completed_sessions)} charging history records for driver {driver_id}")
            return completed_sessions

        except Exception as e:
            self.logger.error(f"Failed to get charging history for driver {driver_id}: {e}")
            return []
