"""
Módulo que representa la central de control de toda la solución. Implementa la lógica y gobierno de todo el sistema.
"""

import sys
import os
import time
import uuid
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.SqliteConnection import SqliteConnection
from Common.MessageFormatter import MessageFormatter
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager
from Common.MySocketServer import MySocketServer
from Common.Status import Status
from Core.Central.MessageDispatcher import MessageDispatcher


class EV_Central:
    def __init__(self, logger=None):
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()

        self.logger = logger
        self.socket_server = None
        self.db_manager = None  # 这个用来存储数据库管理对象
        self.db_path = self.config.get_db_path()
        self.sql_schema = os.path.join("Core", "BD", "table.sql")
        self.running = False
        
        self._cp_connections = {}  # {cp_id: client_socket}
        self._client_to_cp = {}  # {client_id: cp_id}
        if not self.debug_mode:
            self.tools = AppArgumentParser(
                app_name="EV_Central",
                description="Sistema Central de Control para Puntos de Recarga de Vehículos Eléctricos",
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
                broker = self.config.get_broker()
                db = self.config.get_db()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

    def _init_database(self):
        self.logger.debug("Initializing database connection")
        try:
            # 连接到 SQLite 数据库
            # 对这个属性进行操作，而不是直接使用 SqliteConnection 类
            self.db_manager = SqliteConnection(
                db_path=self.db_path,
                sql_schema_file=self.sql_schema,
                create_tables_if_not_exist=True,
            )
            if not self.db_manager.is_sqlite_available():
                self.logger.error(
                    "Database is not available or not properly initialized."
                )
                sys.exit(1)

            self.db_manager.set_all_charging_points_status(Status.DISCONNECTED.value)
            charging_points_count = len(self.db_manager.get_all_charging_points())
            self.logger.info(
                f"Database initialized successfully. {charging_points_count} charging points set to DISCONNECTED."
            )

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)

    def _init_socket_server(self):
        """
        Initialize the socket server to listen for incoming connections from charging points.
        """
        self.logger.debug("Initializing socket server")

        try:
            # 将自定义消息处理函数分配给 socket 服务器
            self.socket_server = MySocketServer(
                host=self.config.get_ip_port_ev_cp_central()[0],
                port=self.config.get_ip_port_ev_cp_central()[1],
                logger=self.logger,
                message_callback=self._process_charging_point_message,
                disconnect_callback=self._handle_client_disconnect,
            )
            # 通过MySocketServer类的start方法启动服务器
            self.socket_server.start()
            self.running = True
            self.logger.debug("Socket server initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize socket server: {e}")
            sys.exit(1)
        self.message_dispatcher = MessageDispatcher(
            logger=self.logger,
            db_manager=self.db_manager,
            socket_server=self.socket_server,
            charging_points_connections=self._cp_connections,
            client_to_ref=self._client_to_cp,
        )

    def _handle_client_disconnect(self, client_id):
        """处理客户端断开连接"""
        if client_id in self._client_to_cp:
            cp_id = self._client_to_cp[client_id]
            self.logger.info(f"Client {client_id} (CP: {cp_id}) disconnected")

            # 更新数据库状态为离线
            try:
                self.db_manager.update_charging_point_status(
                    cp_id=cp_id,
                    status=Status.DISCONNECTED.value,
                )
                self.logger.info(f"Charging point {cp_id} set to DISCONNECTED.")
            except Exception as e:
                self.logger.error(f"Failed to update status for {cp_id}: {e}")

            # 清理映射关系
            del self._cp_connections[cp_id]
            del self._client_to_cp[client_id]

    def _process_charging_point_message(self, client_id, message):
        """
        作为消息的分发中心。根据消息的 'type' 字段，调用相应的处理方法。
        """
        self.logger.info(f"收到来自客户端 {client_id} 的消息: {message}")

        return self.message_dispatcher.dispatch_message(client_id, message)

    def _init_kafka_producer(self):  # TODO: implement
        self.logger.debug("Initializing Kafka producer")
        pass

    def _init_kafka_consumer(self):  # TODO: implement
        self.logger.debug("Initializing Kafka consumer")
        pass

    def initialize_systems(self):
        self.logger.info("Initializing systems...")
        self._init_database()
        self._init_socket_server()

        # self._init_kafka_producer()
        # self._init_kafka_consumer()
        self.logger.info("All systems initialized successfully.")

    def shutdown_systems(self):
        self.logger.info("Shutting down systems...")
        if self.socket_server:
            self.socket_server.stop()
        if self.db_manager:
            try:
                self.db_manager.set_all_charging_points_status(
                    Status.DISCONNECTED.value
                )
                self.logger.info("All charging points set to DISCONNECTED.")
            except Exception as e:
                self.logger.error(f"Error setting charging points to DISCONNECTED: {e}")
        self.running = False

    def start(self):
        self.logger.debug(f"Starting EV Central on port {self.args.listen_port}")
        self.logger.debug(
            f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )
        self.logger.debug(
            f"Connecting to Database at {self.args.db[0]}:{self.args.db[1]}"
        )

        self.initialize_systems()


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    ev_central = EV_Central(logger=logger)

    try:
        ev_central.start()
        ev_central.logger.info(
            "EV Central main process is now idling, waiting for KeyboardInterrupt or external stop signal."
        )

        while ev_central.socket_server.running_event.is_set():
            time.sleep(0.1)

        ev_central.logger.info("EV Central main loop finished.")

    except KeyboardInterrupt:
        ev_central.logger.info("Shutting down EV Central due to KeyboardInterrupt.")
    finally:
        ev_central.shutdown_systems()
        sys.exit(0)
