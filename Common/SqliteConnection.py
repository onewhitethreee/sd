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
            logging.debug(f"Database file '{self.db_path}' does not exist. Attempting to create and set up schema.")
            self._execute_sql_from_file()
        else:
            logging.debug(f"Database file '{self.db_path}' already exists. Skipping initial schema creation.")

    def get_connection(self):
        """为每个线程获取独立的连接"""
        if not hasattr(self.local, "connection") or self.local.connection is None:
            self.local.connection = sqlite3.connect(self.db_path)
            self.local.connection.execute("PRAGMA foreign_keys = ON;")
            thread_id = threading.current_thread().ident
            logging.debug(f"Created new connection for thread {thread_id}")
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
        logging.debug(f"Checking availability of SQLite database at '{self.db_path}'.")
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
            logging.error(f"SQLite error while checking availability of '{self.db_path}': {e}")
            return False
        except Exception as e: 
            logging.error(f"An unexpected error occurred during availability check: {e}")
            return False
        finally:
            if self.connection:
                self.connection.close()
                logging.debug(f"Connection to database '{self.db_path}' closed after availability check.")

    def get_all_charging_points(self):
        """获取所有充电桩"""
        connection = self.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT cp_id, location, price_per_kwh, status, last_connection_time FROM ChargingPoints"
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "location": row[1],
                    "price_per_kwh": row[2],
                    "status": row[3],
                    "last_connection_time": row[4],
                }
                for row in rows
            ]
        except Exception as e:
            logging.error(f"Error fetching charging points: {e}")
            return []

    def clean_database(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def insert_or_update_charging_point(self, cp_id, location, price_per_kwh, status, last_connection_time):
        """插入或更新充电桩信息"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            # 使用 INSERT OR REPLACE 来处理重复
            cursor.execute("""
                INSERT OR REPLACE INTO ChargingPoints 
                (cp_id, location, price_per_kwh, status, last_connection_time)
                VALUES (?, ?, ?, ?, ?)
            """, (cp_id, location, price_per_kwh, status, last_connection_time))
            
            connection.commit()
            
            
            logging.info(f"充电桩 {cp_id} 注册/更新成功, 位置: {location}, 价格: {price_per_kwh}, 状态: {status}, 时间: {last_connection_time}, rows affected: {cursor.rowcount}")
            
            return True
            
        except Exception as e:
            connection.rollback()
            logging.error(f"Error inserting/updating charging point '{cp_id}': {e}")
            raise



if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    db_file = "test.db"
    sql_schema_file_path = os.path.join("Core", "BD", "table.sql")

    db_manager_new = SqliteConnection(db_path=db_file, sql_schema_file=sql_schema_file_path, create_tables_if_not_exist=True)

    if db_manager_new.is_sqlite_available():
        logging.info("SUCCESS: SQLite database is available and tables are set up.")
    else:
        logging.error("FAILURE: SQLite database is not available or setup failed.")
        db_manager_new.clean_database()
