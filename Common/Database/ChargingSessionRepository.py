"""
ChargingSessionRepository - 负责 ChargingSessions 表的所有数据库操作
"""

import logging
from datetime import datetime
from Common.Database.BaseRepository import BaseRepository


class ChargingSessionRepository(BaseRepository):
    """
    充电会话数据访问层，封装所有与ChargingSessions表相关的数据库操作
    """

    def get_table_name(self):
        return "ChargingSessions"

    def create(self, session_id, cp_id, driver_id, start_time):
        """
        创建充电会话

        Args:
            session_id: 会话ID
            cp_id: 充电桩ID
            driver_id: 司机ID
            start_time: 开始时间

        Returns:
            bool: 是否成功
        """
        try:
            query = """
                INSERT INTO ChargingSessions
                (session_id, cp_id, driver_id, start_time, status)
                VALUES (?, ?, ?, ?, ?)
            """
            self.execute_update(query, (session_id, cp_id, driver_id, start_time, "in_progress"))

            self.logger.info(f"充电会话 {session_id} 创建成功")
            return True
        except Exception as e:
            self.logger.error(f"创建充电会话 {session_id} 失败: {e}")
            return False

    def update(
        self,
        session_id,
        end_time=None,
        energy_consumed_kwh=None,
        total_cost=None,
        status=None,
    ):
        """
        更新充电会话

        Args:
            session_id: 会话ID
            end_time: 结束时间（可选）
            energy_consumed_kwh: 消耗电量（可选）
            total_cost: 总费用（可选）
            status: 状态（可选）

        Returns:
            bool: 是否成功
        """
        try:
            # 构建动态更新语句
            updates = []
            params = []

            if end_time is not None:
                updates.append("end_time = ?")
                params.append(end_time)

            if energy_consumed_kwh is not None:
                updates.append("energy_consumed_kwh = ?")
                params.append(energy_consumed_kwh)

            if total_cost is not None:
                updates.append("total_cost = ?")
                params.append(total_cost)

            if status is not None:
                updates.append("status = ?")
                params.append(status)

            if not updates:
                self.logger.warning(f"更新会话 {session_id} 时没有提供任何字段")
                return False

            params.append(session_id)
            query = f"UPDATE ChargingSessions SET {', '.join(updates)} WHERE session_id = ?"

            self.execute_update(query, params)
            self.logger.info(f"充电会话 {session_id} 更新成功")
            return True
        except Exception as e:
            self.logger.error(f"更新充电会话 {session_id} 失败: {e}")
            return False

    def get_by_id(self, session_id):
        """
        根据ID获取充电会话信息

        Args:
            session_id: 会话ID

        Returns:
            dict: 会话信息，如果不存在返回None
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE session_id = ?
            """
            rows = self.execute_query(query, (session_id,))

            if rows:
                row = rows[0]
                return {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
            return None
        except Exception as e:
            self.logger.error(f"获取充电会话 {session_id} 失败: {e}")
            return None

    def get_active_sessions(self):
        """
        获取所有活跃的充电会话

        Returns:
            list: 活跃会话列表
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE status = 'in_progress'
            """
            rows = self.execute_query(query)

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"获取活跃充电会话失败: {e}")
            return []

    def get_all(self):
        """
        获取所有充电会话（包括历史会话）

        Returns:
            list: 所有会话列表
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                ORDER BY start_time DESC
            """
            rows = self.execute_query(query)

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"获取所有充电会话失败: {e}")
            return []

    def get_active_sessions_by_charging_point(self, cp_id):
        """
        获取充电桩的所有活跃会话

        Args:
            cp_id: 充电桩ID

        Returns:
            list: 活跃会话列表
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE cp_id = ? AND status = 'in_progress'
            """
            rows = self.execute_query(query, (cp_id,))

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"获取充电桩 {cp_id} 的活跃会话失败: {e}")
            return []

    def get_active_sessions_by_driver(self, driver_id):
        """
        获取司机的所有活跃会话

        Args:
            driver_id: 司机ID

        Returns:
            list: 活跃会话列表
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE driver_id = ? AND status = 'in_progress'
            """
            rows = self.execute_query(query, (driver_id,))

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"获取司机 {driver_id} 的活跃会话失败: {e}")
            return []

    def get_sessions_by_charging_point(self, cp_id):
        """
        获取充电桩的所有会话（包括历史会话）

        Args:
            cp_id: 充电桩ID

        Returns:
            list: 会话列表
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE cp_id = ?
                ORDER BY start_time DESC
            """
            rows = self.execute_query(query, (cp_id,))

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"获取充电桩 {cp_id} 的会话失败: {e}")
            return []

    def get_sessions_by_driver(self, driver_id):
        """
        获取司机的所有会话（包括历史会话）

        Args:
            driver_id: 司机ID

        Returns:
            list: 会话列表
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE driver_id = ?
                ORDER BY start_time DESC
            """
            rows = self.execute_query(query, (driver_id,))

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"获取司机 {driver_id} 的会话失败: {e}")
            return []

    def exists(self, session_id):
        """
        检查会话是否存在

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否存在
        """
        try:
            query = "SELECT 1 FROM ChargingSessions WHERE session_id = ?"
            rows = self.execute_query(query, (session_id,))
            return len(rows) > 0
        except Exception as e:
            self.logger.error(f"检查会话 {session_id} 是否存在失败: {e}")
            return False

    def is_active(self, session_id):
        """
        检查会话是否活跃

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否活跃
        """
        try:
            session = self.get_by_id(session_id)
            return session is not None and session["status"] == "in_progress"
        except Exception as e:
            self.logger.error(f"检查会话 {session_id} 是否活跃失败: {e}")
            return False
