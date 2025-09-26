"""
Módulo que representa la central de control de toda la solución. Implementa la lógica y gobierno de todo el sistema.
"""

import sys
import os
from datetime import datetime


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.SqliteConnection import SqliteConnection
from Common.MessageFormatter import MessageFormatter
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager

class EV_Central:
    def __init__(self, logger=None):
        self.logger = logger
        self.config = ConfigManager() 
        self.debug_mode = self.config.get_debug_mode()
        if not self.debug_mode:
            self.tools = AppArgumentParser(
                "EV_Central",
                "Sistema Central de Control para Puntos de Recarga de Vehículos Eléctricos",
            )
            self.tools.add_argument("listen_port", type=int, help="Puerto de escuha")
            self.tools.add_argument(
                "broker",
                type=ip_port_type,
                help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)",
            )
            self.tools.add_argument(
                "--db",
                type=ip_port_type,
                help="IP y puerto del servidor de base de datos (formato IP:PORT)",
                default=("localhost", 5432),
            )
            self.args = self.tools.parse_args()
            
        else:
            class Args:
                listen_port = self.config.get_listen_port()
                broker = self.config.get_broker_address(), self.config.get_broker_port()
                db = self.config.get_db_address(), self.config.get_db_port()
            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        self.db_connection = None
        self.db_path = self.config.get_db_path()
        self.sql_schema = os.path.join("Core", "BD", "table.sql")
        self.charging_points = {}

    def _init_database(self):
        self.logger.debug("Initializing database connection")
        try:
            self.db_connection = self.db_connection_manager = SqliteConnection(
                db_path=self.db_path,
                sql_schema_file=self.sql_schema,
                create_tables_if_not_exist=True,
            )
            if not self.db_connection.is_sqlite_available():
                self.logger.error("Database is not available or not properly initialized.")
                sys.exit(1)
            self.logger.debug("Database connection initialized successfully")

            self.charging_points = self.get_all_registered_charging_points()
            for cp in self.charging_points:
                self.logger.info(
                    f"Registered Charging Point: ID={cp['id']}, Location={cp['location']}, Price={cp['price_per_kwh']}, Status={cp['status']}, Last Connection={cp['last_connection_time']}"
                )
                
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)

    def get_all_registered_charging_points(self):
        """
        Retrieve all registered charging points from the database.
        Returns a list of dictionaries with charging point details.
        """
        if not self.db_connection:
            self.logger.error("Database connection is not initialized.")
            return []
        
        if not self.debug_mode:
            return SqliteConnection.get_all_charging_points(self.db_connection)
        else:
            """
            Simulated data for debug mode.
            """
            self.logger.debug("Fetching all registered charging points from the debug mode database")
            return [
                {"id": "CP001", "location": "Calle Mayor 1", "price_per_kwh": 0.15, "status": "DESCONECTADO", "last_connection_time": None},
                {
                    "id": "CP002",
                    "location": "Avenida Central 5",
                    "price_per_kwh": 0.20,
                    "status": "DESCONECTADO",
                    "last_connection_time": None
                },
                {"id": "CP003", "location": "Plaza Mayor 10", "price_per_kwh": 0.25, "status": "DESCONECTADO", "last_connection_time": datetime.now()},
            ]

    def _init_kafka_producer(self):
        self.logger.debug("Initializing Kafka producer")
        pass

    def _init_kafka_consumer(self):
        self.logger.debug("Initializing Kafka consumer")
        pass

    def initialize_systems(self):
        self.logger.info("Initializing systems...")
        self._init_database()
        
        self._init_kafka_producer()
        self._init_kafka_consumer()

    def start(self):
        self.logger.debug(f"Starting EV Central on port {self.args.listen_port}")
        self.logger.debug(f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}")
        self.logger.debug(f"Connecting to Database at {self.args.db[0]}:{self.args.db[1]}")

        self.initialize_systems()

        
        try:
            ## SOCKET HERE ##
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            self.logger.info("Shutting down EV Central")
            sys.exit(0)


if __name__ == "__main__":

    logger = CustomLogger.get_logger()
    ev_central = EV_Central(logger=logger)
    ev_central.start()
