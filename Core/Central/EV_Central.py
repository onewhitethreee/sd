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
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        if self.debug_mode == "False":
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
                listen_port = 5000
                broker = ("localhost", 9092)
                db = ("localhost", 5432)
            self.args = Args()
            logger.debug("Debug mode is ON. Using default arguments.")

        self.db_connection = None
        self.db_path = "ev_central.db"
        self.sql_schema = os.path.join("Core", "BD", "table.sql")
        self.charging_points = {}

    def _init_database(self):
        logger.debug("Initializing database connection")
        try:
            self.db_connection = self.db_connection_manager = SqliteConnection(
                db_path=self.db_path,
                sql_schema_file=self.sql_schema,
                create_tables_if_not_exist=True,
            )
            if not self.db_connection.is_sqlite_available():
                logger.error("Database is not available or not properly initialized.")
                sys.exit(1)
            logger.debug("Database connection initialized successfully")

            self.charging_points = self.get_all_registered_charging_points()
            for cp in self.charging_points:
                logger.info(
                    f"Registered Charging Point: ID={cp['id']}, Location={cp['location']}, Price={cp['price_per_kwh']}, Status={cp['status']}, Last Connection={cp['last_connection_time']}"
                )
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)

    def get_all_registered_charging_points(self):
        """
        Retrieve all registered charging points from the database.
        Returns a list of dictionaries with charging point details.
        """
        if not self.db_connection:
            logger.error("Database connection is not initialized.")
            return []
        
        if not self.debug_mode:
            return SqliteConnection.get_all_charging_points(self.db_connection)
        else:
            """
            Simulated data for debug mode.
            """
            logger.debug("Fetching all registered charging points from the debug mode database")
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
        logger.debug("Initializing Kafka producer")
        pass

    def _init_kafka_consumer(self):
        logger.debug("Initializing Kafka consumer")
        pass

    def initialize_systems(self):
        logger.info("Initializing systems...")
        self._init_database()
        
        self._init_kafka_producer()
        self._init_kafka_consumer()

    def start(self):
        logger.debug(f"Starting EV Central on port {self.args.listen_port}")
        logger.debug(f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}")
        logger.debug(f"Connecting to Database at {self.args.db[0]}:{self.args.db[1]}")

        self.initialize_systems()

        # Aquí iría la lógica para iniciar la central, escuchar en el puerto, conectar a la base de datos, etc.
        try:
            ## SOCKET HERE ##
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            logger.info("Shutting down EV Central")
            sys.exit(0)


if __name__ == "__main__":
    config = ConfigManager()

    logger = CustomLogger.get_logger()
    ev_central = EV_Central(debug_mode=config.get("DEBUG_MODE"))
    ev_central.start()
