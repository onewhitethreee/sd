import sqlite3
import os
import logging


class SqliteConnection:
    def __init__(self, db_path, sql_schema_file=None, create_tables_if_not_exist=True):
        self.db_path = db_path 
        self.sql_schema_file = sql_schema_file
        self.connection = None
        self.create_tables_if_not_exist = create_tables_if_not_exist


        if self.create_tables_if_not_exist and not os.path.exists(self.db_path):
            logging.debug(f"Database file '{self.db_path}' does not exist. Attempting to create and set up schema.")
            self._execute_sql_from_file()
        else:
            logging.debug(f"Database file '{self.db_path}' already exists. Skipping initial schema creation.")
        

    def _execute_sql_from_file(self):
        """
        Create tables in the SQLite database by executing SQL commands from a file.
        """
        if not self.sql_schema_file:
            logging.error("No SQL schema file provided, cannot create tables.")
            return
        if not os.path.exists(self.sql_schema_file):
            logging.error(f"SQL schema file '{self.sql_schema_file}' not found.")
            return

        logging.debug(f"Executing SQL schema from '{self.sql_schema_file}' into database '{self.db_path}'.")
        try:
            self.connection = sqlite3.connect(self.db_path)
            
            self.connection.execute("PRAGMA foreign_keys = ON;") 
            
            cursor = self.connection.cursor()

            with open(self.sql_schema_file, 'r', encoding='utf-8') as f:
                sql_script = f.read()

            cursor.executescript(sql_script) 

            self.connection.commit()
            logging.debug(f"Successfully executed SQL schema from '{self.sql_schema_file}'.")

        except sqlite3.Error as e:
            logging.error(f"SQLite error during schema execution: {e}")
            if self.connection:
                self.connection.rollback() 
        except FileNotFoundError:
            logging.error(f"SQL schema file '{self.sql_schema_file}' not found during read operation.")
        except Exception as e: 
            logging.error(f"An unexpected error occurred: {e}")
        finally:
            if self.connection:
                self.connection.close()
                logging.debug(f"Connection to database '{self.db_path}' closed.")



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

    def clean_database(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    db_file = "test.db"
    sql_schema_file_path = (
        r"Core\BD\table.sql"
    )

    db_manager_new = SqliteConnection(db_path=db_file, sql_schema_file=sql_schema_file_path, create_tables_if_not_exist=True)

    if db_manager_new.is_sqlite_available():
        logging.info("SUCCESS: SQLite database is available and tables are set up.")
    else:
        logging.error("FAILURE: SQLite database is not available or setup failed.")
        db_manager_new.clean_database()
