"""
Módulo que representa la central de control de toda la solución. Implementa la lógica y gobierno de todo el sistema.
"""

import sys
import os
import time
import uuid
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Config.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.Database.SqliteConnection import SqliteConnection
from Common.Config.CustomLogger import CustomLogger
from Common.Config.ConfigManager import ConfigManager
from Common.Network.MySocketServer import MySocketServer
from Common.Config.Status import Status
from Common.Queue.KafkaManager import KafkaManager, KafkaTopics
from Core.Central.MessageDispatcher import MessageDispatcher


class EV_Central:
    def __init__(self, logger=None):
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()

        self.logger = logger
        self.socket_server = None

        self.db_manager = None  # 这个用来存储数据库管理对象
        self.kafka_manager = None  # Kafka管理器
        self.message_dispatcher = None  # 消息分发器
        self.db_path = self.config.get_db_path()
        self.sql_schema = os.path.join("Core", "BD", "table.sql")
        self.running = False

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
        try:
            # 连接到 SQLite 数据库
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

        # 初始化消息分发器
        self.message_dispatcher = MessageDispatcher(
            logger=self.logger,
            db_manager=self.db_manager,
            socket_server=self.socket_server,
        )

    def _handle_client_disconnect(self, client_id):
        """处理客户端断开连接"""
        # 使用ChargingPoint管理器处理断开连接
        cp_id = self.message_dispatcher.charging_point_manager.handle_client_disconnect(
            client_id
        )

        if cp_id:
            self.logger.info(f"Client {client_id} (CP: {cp_id}) disconnected")
            self.logger.info(f"Charging point {cp_id} set to DISCONNECTED.")

    def _process_charging_point_message(self, client_id, message):
        """
        作为消息的分发中心。根据消息的 'type' 字段，调用相应的处理方法。
        """
        # 消息已经是字典格式（JSON）
        self.logger.info(f"收到来自客户端 {client_id} 的消息: {message}")

        return self.message_dispatcher.dispatch_message(client_id, message)

    def _init_kafka_producer(self):
        """初始化Kafka生产者"""
        self.logger.debug("Initializing Kafka producer")
        try:
            broker_address = f"{self.args.broker[0]}:{self.args.broker[1]}"
            self.kafka_manager = KafkaManager(broker_address, self.logger)

            if self.kafka_manager.init_producer():
                self.logger.info("Kafka producer initialized successfully")
                return True
            else:
                self.logger.error("Failed to initialize Kafka producer")
                return False
        except Exception as e:
            self.logger.error(f"Error initializing Kafka producer: {e}")
            return False

    def _init_kafka_consumer(self):
        """初始化Kafka消费者"""
        self.logger.debug("Initializing Kafka consumer")
        try:
            if not self.kafka_manager:
                self.logger.error("Kafka manager not initialized")
                return False

            # 启动Kafka管理器
            self.kafka_manager.start()

            # 初始化消费者订阅相关主题
            topics_to_subscribe = [
                (KafkaTopics.CHARGING_POINT_HEARTBEAT, "central_group"),
                (KafkaTopics.CHARGING_POINT_FAULT, "central_group"),
                (KafkaTopics.SYSTEM_ALERTS, "central_group"),
            ]

            for topic, group_id in topics_to_subscribe:
                self.kafka_manager.init_consumer(
                    topic, group_id, self._handle_kafka_message
                )

            self.logger.info("Kafka consumers initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error initializing Kafka consumer: {e}")
            return False

    def _handle_kafka_message(self, message):
        """处理来自Kafka的消息"""
        try:
            self.logger.debug(f"Received Kafka message: {message}")
            # 这里可以添加具体的消息处理逻辑
        except Exception as e:
            self.logger.error(f"Error handling Kafka message: {e}")

    def initialize_systems(self):
        self.logger.info("Initializing systems...")
        self._init_database()
        self._init_socket_server()

        # 初始化Kafka
        # if self._init_kafka_producer():
        #     self._init_kafka_consumer()
        # else:
        #     self.logger.warning(
        #         "Kafka initialization failed, continuing without Kafka support"
        #     )

        self.logger.info("All systems initialized successfully.")

    def shutdown_systems(self):
        self.logger.info("Shutting down systems...")
        if self.socket_server:
            self.socket_server.stop()
        if self.kafka_manager:
            self.kafka_manager.stop()
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
        # self.logger.debug(
        #     f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        # )

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
