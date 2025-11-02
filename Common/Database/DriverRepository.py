"""
DriverRepository - 负责 Drivers 表的所有数据库操作
"""

from datetime import datetime
from Common.Database.BaseRepository import BaseRepository


class DriverRepository(BaseRepository):
    """
    司机数据访问层，封装所有与Drivers表相关的数据库操作
    """

    def get_table_name(self):
        return "Drivers"

    def register(self, driver_id, username):
        """
        注册司机

        Args:
            driver_id: 司机ID
            username: 用户名

        Returns:
            bool: 是否成功
        """
        try:
            current_time = datetime.now().isoformat()

            query = """
                INSERT OR REPLACE INTO Drivers
                (driver_id, username, created_at)
                VALUES (?, ?, ?)
            """
            self.execute_update(query, (driver_id, username, current_time))

            self.logger.info(f"司机 {driver_id} 注册成功")
            return True
        except Exception as e:
            self.logger.error(f"注册司机 {driver_id} 失败: {e}")
            return False

    def get_by_id(self, driver_id):
        """
        根据ID获取司机信息

        Args:
            driver_id: 司机ID

        Returns:
            dict: 司机信息，如果不存在返回None
        """
        try:
            query = """
                SELECT driver_id, username, created_at
                FROM Drivers
                WHERE driver_id = ?
            """
            rows = self.execute_query(query, (driver_id,))

            if rows:
                row = rows[0]
                return {
                    "driver_id": row[0],
                    "username": row[1],
                    "created_at": row[2],
                }
            return None
        except Exception as e:
            self.logger.error(f"获取司机 {driver_id} 信息失败: {e}")
            return None

    def exists(self, driver_id):
        """
        检查司机是否存在

        Args:
            driver_id: 司机ID

        Returns:
            bool: 是否存在
        """
        try:
            query = "SELECT 1 FROM Drivers WHERE driver_id = ?"
            rows = self.execute_query(query, (driver_id,))
            return len(rows) > 0
        except Exception as e:
            self.logger.error(f"检查司机 {driver_id} 是否存在失败: {e}")
            return False

    def get_all(self):
        """
        获取所有司机

        Returns:
            list: 司机列表
        """
        try:
            query = """
                SELECT driver_id, username, created_at
                FROM Drivers
            """
            rows = self.execute_query(query)

            return [
                {
                    "driver_id": row[0],
                    "username": row[1],
                    "created_at": row[2],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"获取所有司机失败: {e}")
            return []

    def update_username(self, driver_id, new_username):
        """
        更新司机用户名

        Args:
            driver_id: 司机ID
            new_username: 新用户名

        Returns:
            bool: 是否成功
        """
        try:
            query = "UPDATE Drivers SET username = ? WHERE driver_id = ?"
            self.execute_update(query, (new_username, driver_id))
            self.logger.info(f"司机 {driver_id} 用户名已更新为 {new_username}")
            return True
        except Exception as e:
            self.logger.error(f"更新司机 {driver_id} 用户名失败: {e}")
            return False

    def delete(self, driver_id):
        """
        删除司机（注意：由于外键约束，需要先删除相关的充电会话）

        Args:
            driver_id: 司机ID

        Returns:
            bool: 是否成功
        """
        try:
            query = "DELETE FROM Drivers WHERE driver_id = ?"
            self.execute_update(query, (driver_id,))
            self.logger.info(f"司机 {driver_id} 已删除")
            return True
        except Exception as e:
            self.logger.error(f"删除司机 {driver_id} 失败: {e}")
            return False

