import sqlite3
import os
import logging
import threading


class SqliteConnection:
    """
    Clase para gestionar conexiones SQLite 
    """
    def __init__(self, db_path, sql_schema_file=None, create_tables_if_not_exist=True):
        """
        Inicializar la conexión a la base de datos SQLite.
        Args:
            db_path: Ruta al archivo de la base de datos SQLite
            sql_schema_file: Archivo SQL para crear la estructura de la base de datos
            create_tables_if_not_exist: Si es True, crea las tablas si no existen
        """
        self.db_path = db_path
        self.sql_schema_file = sql_schema_file
        self.connection = None
        self.create_tables_if_not_exist = create_tables_if_not_exist
        # usar threading.local() para resolver el problema de SQLite con múltiples hilos. Este problema ha sido detectado en servidores socket multihilo.
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
        """Obtener una conexión independiente para cada hilo"""
        if not hasattr(self.local, "connection") or self.local.connection is None:
        
            self.local.connection = sqlite3.connect(
                self.db_path, check_same_thread=False
            )
            self.local.connection.execute("PRAGMA foreign_keys = ON;")
            thread_id = threading.current_thread().ident
            # logging.debug(f"Created new connection for thread {thread_id}")
        return self.local.connection

   
    def _execute_sql_from_file(self):
        """
        Crear la estructura de la tabla (modificado: usar conexión temporal)
        """
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

    
                


