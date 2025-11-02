"""
ChargingPointRepository - 负责 ChargingPoints 表的所有数据库操作
"""

import logging
from datetime import datetime, timezone
from Common.Database.BaseRepository import BaseRepository


class ChargingPointRepository(BaseRepository):
    """
    充电桩数据访问层，封装所有与ChargingPoints表相关的数据库操作
    """

    def get_table_name(self):
        return "ChargingPoints"

    def insert_or_update(
        self,
        cp_id,
        location,
        price_per_kwh,
        status,
        last_connection_time,
        max_charging_rate_kw=11.0,
    ):
        """
        插入或更新充电桩信息

        Args:
            cp_id: 充电桩ID
            location: 位置
            price_per_kwh: 每度电价格
            status: 状态
            last_connection_time: 最后连接时间
            max_charging_rate_kw: 最大充电速率（千瓦）

        Returns:
            bool: 是否成功
        """
        try:
            query = """
                INSERT OR REPLACE INTO ChargingPoints
                (cp_id, location, price_per_kwh, max_charging_rate_kw, status, last_connection_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            self.execute_update(
                query,
                (
                    cp_id,
                    location,
                    price_per_kwh,
                    max_charging_rate_kw,
                    status,
                    last_connection_time,
                ),
            )

            self.logger.info(
                f"充电桩 {cp_id} 注册/更新成功, 位置: {location}, 价格: {price_per_kwh}, "
                f"最大充电速率: {max_charging_rate_kw}kW, 状态: {status}"
            )
            return True

        except Exception as e:
            self.logger.error(f"插入/更新充电桩 '{cp_id}' 失败: {e}")
            return False

    def update_status(self, cp_id, status, last_connection_time=None):
        """
        更新充电桩状态

        Args:
            cp_id: 充电桩ID
            status: 新状态
            last_connection_time: 最后连接时间（可选）

        Returns:
            bool: 是否成功
        """
        try:
            if last_connection_time is not None:
                query = "UPDATE ChargingPoints SET status = ?, last_connection_time = ? WHERE cp_id = ?"
                self.execute_update(query, (status, last_connection_time, cp_id))
            else:
                query = "UPDATE ChargingPoints SET status = ? WHERE cp_id = ?"
                self.execute_update(query, (status, cp_id))

            return True
        except Exception as e:
            self.logger.error(f"更新充电桩 {cp_id} 状态失败: {e}")
            return False

    def update_last_connection_time(self, cp_id, last_connection_time):
        """
        更新充电桩的最后连接时间

        Args:
            cp_id: 充电桩ID
            last_connection_time: 最后连接时间

        Returns:
            bool: 是否成功
        """
        try:
            query = "UPDATE ChargingPoints SET last_connection_time = ? WHERE cp_id = ?"
            self.execute_update(query, (last_connection_time, cp_id))
            return True
        except Exception as e:
            self.logger.error(f"更新充电桩 {cp_id} 连接时间失败: {e}")
            return False

    def get_by_id(self, cp_id):
        """
        根据ID获取充电桩信息

        Args:
            cp_id: 充电桩ID

        Returns:
            dict: 充电桩信息，如果不存在返回None
        """
        try:
            query = """
                SELECT cp_id, location, price_per_kwh, max_charging_rate_kw, status, last_connection_time
                FROM ChargingPoints
                WHERE cp_id = ?
            """
            rows = self.execute_query(query, (cp_id,))

            if rows:
                row = rows[0]
                return {
                    "cp_id": row[0],
                    "location": row[1],
                    "price_per_kwh": row[2],
                    "max_charging_rate_kw": row[3],
                    "status": row[4],
                    "last_connection_time": row[5],
                }
            return None
        except Exception as e:
            self.logger.error(f"获取充电桩 {cp_id} 信息失败: {e}")
            return None

    def get_status(self, cp_id):
        """
        获取充电桩状态

        Args:
            cp_id: 充电桩ID

        Returns:
            str: 充电桩状态，如果不存在返回None
        """
        try:
            query = "SELECT status FROM ChargingPoints WHERE cp_id = ?"
            rows = self.execute_query(query, (cp_id,))
            return rows[0][0] if rows else None
        except Exception as e:
            self.logger.error(f"获取充电桩 {cp_id} 状态失败: {e}")
            return None

    def exists(self, cp_id):
        """
        检查充电桩是否存在

        Args:
            cp_id: 充电桩ID

        Returns:
            bool: 是否存在
        """
        try:
            query = "SELECT 1 FROM ChargingPoints WHERE cp_id = ?"
            rows = self.execute_query(query, (cp_id,))
            return len(rows) > 0
        except Exception as e:
            self.logger.error(f"检查充电桩 {cp_id} 是否存在失败: {e}")
            return False

    def get_all(self):
        """
        获取所有充电桩

        Returns:
            list: 充电桩列表
        """
        try:
            query = """
                SELECT cp_id, location, price_per_kwh, status, last_connection_time, max_charging_rate_kw
                FROM ChargingPoints
            """
            rows = self.execute_query(query)

            return [
                {
                    "cp_id": row[0],
                    "location": row[1],
                    "price_per_kwh": row[2],
                    "status": row[3],
                    "last_connection_time": row[4],
                    "max_charging_rate_kw": row[5],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"获取所有充电桩失败: {e}")
            return []

    def get_available(self):
        """
        获取所有可用的充电桩（状态为ACTIVE）

        Returns:
            list: 可用充电桩列表
        """
        try:
            query = """
                SELECT cp_id, location, price_per_kwh, max_charging_rate_kw, status, last_connection_time
                FROM ChargingPoints
                WHERE status = ?
            """
            rows = self.execute_query(query, ("ACTIVE",))

            return [
                {
                    "cp_id": row[0],
                    "location": row[1],
                    "price_per_kwh": row[2],
                    "max_charging_rate_kw": row[3],
                    "status": row[4],
                    "last_connection_time": row[5],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"获取可用充电桩失败: {e}")
            return []

    def set_all_status(self, status):
        """
        设置所有充电桩的状态

        Args:
            status: 新状态

        Returns:
            bool: 是否成功
        """
        try:
            query = "UPDATE ChargingPoints SET status = ?"
            self.execute_update(query, (status,))
            return True
        except Exception as e:
            self.logger.error(f"设置所有充电桩状态失败: {e}")
            return False
