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
                


