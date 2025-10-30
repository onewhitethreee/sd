import sqlite3
import os
import logging
import threading


class SqliteConnection:
    def __init__(self, db_path, sql_schema_file=None, create_tables_if_not_exist=True):
        self.db_path = db_path
        self.sql_schema_file = sql_schema_file
        self.connection = None
        self.create_tables_if_not_exist = create_tables_if_not_exist
        # 用线程池来解决sqlite跨线程使用，这个问题出现在多线程的socket server中
        self.local = threading.local()

        if self.create_tables_if_not_exist and not os.path.exists(self.db_path):
            logging.debug(
                f"Database file '{self.db_path}' does not exist. Attempting to create and set up schema."
            )
            self._execute_sql_from_file()
        else:
            # logging.debug(
            #     f"Database file '{self.db_path}' already exists. Skipping initial schema creation."
            # )
            pass

    def get_connection(self):
        """为每个线程获取独立的连接"""
        if not hasattr(self.local, "connection") or self.local.connection is None:
            # 使用 isolation_level=None 来禁用自动事务，但我们会手动管理事务
            # 实际上，保持默认的 isolation_level="" 来启用自动事务管理
            self.local.connection = sqlite3.connect(
                self.db_path, check_same_thread=False
            )
            self.local.connection.execute("PRAGMA foreign_keys = ON;")
            # 设置 isolation_level 为 None 以禁用隐式事务，但这会导致 autocommit 模式
            # 我们保持默认行为，需要显式 commit()
            thread_id = threading.current_thread().ident
            # logging.debug(f"Created new connection for thread {thread_id}")
        return self.local.connection

    def close_connection(self):
        """关闭数据库连接"""
        if hasattr(self.local, "connection") and self.local.connection is not None:
            self.local.connection.close()
            thread_id = threading.current_thread().ident
            logging.debug(f"Closed connection for thread {thread_id}")
            self.local.connection = None

    def _execute_sql_from_file(self):
        """创建表结构（修改：使用临时连接）"""
        if not self.sql_schema_file or not os.path.exists(self.sql_schema_file):
            logging.error(f"SQL schema file '{self.sql_schema_file}' not found.")
            return
        try:
            temp_conn = sqlite3.connect(self.db_path)
            temp_conn.execute("PRAGMA foreign_keys = ON;")

            with open(self.sql_schema_file, "r", encoding="utf-8") as f:
                sql_script = f.read()

            temp_conn.executescript(sql_script)
            temp_conn.commit()
            logging.debug(
                f"Successfully executed SQL schema from '{self.sql_schema_file}'."
            )

        except Exception as e:
            logging.error(f"Error during schema execution: {e}")
            raise
        finally:
            if temp_conn:
                temp_conn.close()

    def is_sqlite_available(self):
        """
        Check if the SQLite database is available and has the expected tables.
        Returns True if available, False otherwise.
        """
        try:
            self.connection = sqlite3.connect(self.db_path)
            cursor = self.connection.cursor()

            cursor.execute("select 1")
            result = cursor.fetchone()
            if result is None:
                logging.error(f"Database '{self.db_path}' is not responding correctly.")
                return False

            required_tables = {"ChargingPoints", "Drivers", "ChargingSessions"}
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('ChargingPoints','Drivers','ChargingSessions')"
            )
            existing = {row[0] for row in cursor.fetchall()}
            missing = required_tables - existing
            if missing:
                logging.error(f"Missing required tables: {missing}")
                return False

            return True

        except sqlite3.Error as e:
            logging.error(
                f"SQLite error while checking availability of '{self.db_path}': {e}"
            )
            return False
        except Exception as e:
            logging.error(
                f"An unexpected error occurred during availability check: {e}"
            )
            return False
        finally:
            if self.connection:
                self.connection.close()
                

    def get_all_charging_points(self):
        """获取所有充电桩"""
        connection = self.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT cp_id, location, price_per_kwh, status, last_connection_time, max_charging_rate_kw FROM ChargingPoints"
            )
            rows = cursor.fetchall()
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
            logging.error(f"Error fetching charging points: {e}")
            return []

    def get_available_charging_points(self):
        """获取所有可用的充电桩（状态为ACTIVE）"""
        connection = self.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT cp_id, location, price_per_kwh, max_charging_rate_kw, status, last_connection_time FROM ChargingPoints WHERE status = ?",
                ("ACTIVE",),
            )
            rows = cursor.fetchall()
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
            logging.error(f"Error fetching available charging points: {e}")
            return []

    def clean_database(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    # TODO 添加事务实现，防止并发问题
    def insert_or_update_charging_point(
        self,
        cp_id,
        location,
        price_per_kwh,
        status,
        last_connection_time,
        max_charging_rate_kw=11.0,
    ):
        """插入或更新充电桩信息"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            # 使用 INSERT OR REPLACE 来处理重复
            cursor.execute(
                """
                INSERT OR REPLACE INTO ChargingPoints
                (cp_id, location, price_per_kwh, max_charging_rate_kw, status, last_connection_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    cp_id,
                    location,
                    price_per_kwh,
                    max_charging_rate_kw,
                    status,
                    last_connection_time,
                ),
            )

            connection.commit()

            logging.info(
                f"充电桩 {cp_id} 注册/更新成功, 位置: {location}, 价格: {price_per_kwh}, 最大充电速率: {max_charging_rate_kw}kW, 状态: {status}, 时间: {last_connection_time}, rows affected: {cursor.rowcount}"
            )

            return True

        except Exception as e:
            connection.rollback()
            logging.error(f"Error inserting/updating charging point '{cp_id}': {e}")
            raise

    def update_charging_point_status(self, cp_id, status, last_connection_time=None):
        """
        更新充电桩状态

        Args:
            cp_id: 充电桩ID
            status: 新状态
            last_connection_time: 最后连接时间（可选）。如果不提供，则不更新此字段
        """
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            if last_connection_time is not None:
                cursor.execute(
                    "UPDATE ChargingPoints SET status = ?, last_connection_time = ? WHERE cp_id = ?",
                    (status, last_connection_time, cp_id),
                )
            else:
                cursor.execute(
                    "UPDATE ChargingPoints SET status = ? WHERE cp_id = ?",
                    (status, cp_id),
                )

            connection.commit()
            # logging.info(f"充电桩 {cp_id} 状态更新成功: {status}")
            return True
        except Exception as e:
            connection.rollback()
            logging.error(f"更新充电桩 {cp_id} 状态失败: {e}")
            return False

    def get_charging_point(self, cp_id):
        """获取充电桩完整信息"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT cp_id, location, price_per_kwh, max_charging_rate_kw, status, last_connection_time
                FROM ChargingPoints
                WHERE cp_id = ?
                """,
                (cp_id,),
            )
            row = cursor.fetchone()
            if row:
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
            logging.error(f"获取充电桩 {cp_id} 信息失败: {e}")
            return None

    def get_charging_point_status(self, cp_id):
        """获取充电桩状态"""
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT status FROM ChargingPoints WHERE cp_id = ?", (cp_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def is_charging_point_registered(self, cp_id):
        """检查充电桩是否已注册"""
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM ChargingPoints WHERE cp_id = ?", (cp_id,))
        return cursor.fetchone() is not None

    def set_all_charging_points_status(self, status):
        """设置所有充电桩的状态"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("UPDATE ChargingPoints SET status = ? WHERE 1", (status,))
            connection.commit()
            return True
        except Exception as e:
            connection.rollback()
            return False

    def create_charging_session(self, session_id, cp_id, driver_id, start_time):
        """创建充电会话"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO ChargingSessions 
                (session_id, cp_id, driver_id, start_time, status)
                VALUES (?, ?, ?, ?, ?)
            """,
                (session_id, cp_id, driver_id, start_time, "in_progress"),
            )

            connection.commit()
            logging.info(f"充电会话 {session_id} 创建成功")
            return True
        except Exception as e:
            connection.rollback()
            logging.error(f"创建充电会话失败: {e}")
            return False

    def update_charging_session(
        self,
        session_id,
        end_time=None,
        energy_consumed_kwh=None,
        total_cost=None,
        status=None,
    ):
        """更新充电会话"""
        connection = self.get_connection()
        cursor = connection.cursor()
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
                logging.warning("没有提供要更新的字段")
                return False

            params.append(session_id)
            query = (
                f"UPDATE ChargingSessions SET {', '.join(updates)} WHERE session_id = ?"
            )

            cursor.execute(query, params)
            connection.commit()

            logging.info(f"充电会话 {session_id} 更新成功")
            return True
        except Exception as e:
            connection.rollback()
            logging.error(f"更新充电会话失败: {e}")
            return False

    def get_charging_session(self, session_id):
        """获取充电会话信息"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT session_id, cp_id, driver_id, start_time, end_time, 
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions 
                WHERE session_id = ?
            """,
                (session_id,),
            )

            row = cursor.fetchone()
            if row:
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
            logging.error(f"获取充电会话失败: {e}")
            return None

    def get_active_charging_sessions(self):
        """获取所有活跃的充电会话"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE status = 'in_progress'
            """
            )

            rows = cursor.fetchall()
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
            logging.error(f"获取活跃充电会话失败: {e}")
            return []

    def get_all_charging_sessions(self):
        """获取所有充电会话（包括历史会话）"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                ORDER BY start_time DESC
            """
            )

            rows = cursor.fetchall()
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
            logging.error(f"获取所有充电会话失败: {e}")
            return []

    def get_active_sessions_for_charging_point(self, cp_id):
        """获取充电桩的所有活跃会话"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE cp_id = ? AND status = 'in_progress'
                """,
                (cp_id,),
            )
            rows = cursor.fetchall()
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
            logging.error(f"获取充电桩 {cp_id} 的活跃会话失败: {e}")
            return []

    def get_active_sessions_for_driver(self, driver_id):
        """获取司机的所有活跃会话"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE driver_id = ? AND status = 'in_progress'
                """,
                (driver_id,),
            )
            rows = cursor.fetchall()
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
            logging.error(f"获取司机 {driver_id} 的活跃会话失败: {e}")
            return []

    def register_driver(self, driver_id, username):
        """注册司机"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            from datetime import datetime

            current_time = datetime.now().isoformat()

            cursor.execute(
                """
                INSERT OR REPLACE INTO Drivers 
                (driver_id, username, created_at)
                VALUES (?, ?, ?)
            """,
                (driver_id, username, current_time),
            )

            connection.commit()
            logging.info(f"司机 {driver_id} 注册成功")
            return True
        except Exception as e:
            connection.rollback()
            logging.error(f"注册司机失败: {e}")
            return False


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    db_file = "test.db"
    sql_schema_file_path = os.path.join("Core", "BD", "table.sql")

    db_manager_new = SqliteConnection(
        db_path=db_file,
        sql_schema_file=sql_schema_file_path,
        create_tables_if_not_exist=True,
    )

    if db_manager_new.is_sqlite_available():
        logging.info("SUCCESS: SQLite database is available and tables are set up.")
    else:
        logging.error("FAILURE: SQLite database is not available or setup failed.")
        db_manager_new.clean_database()
