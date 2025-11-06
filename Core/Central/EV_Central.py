"""
Módulo que representa la central de control de toda la solución. Implementa la lógica y gobierno de todo el sistema.
"""

import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Config.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.Database.SqliteConnection import SqliteConnection
from Common.Config.CustomLogger import CustomLogger
from Common.Config.ConfigManager import ConfigManager
from Common.Network.MySocketServer import MySocketServer
from Common.Config.Status import Status
from Common.Queue.KafkaManager import KafkaManager, KafkaTopics
from Core.Central.MessageDispatcher import MessageDispatcher
from Core.Central.AdminCLI import AdminCLI


class EV_Central:
    def __init__(self, logger=None):
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()

        self.logger = logger
        self.socket_server = None

        self.db_manager = None  # 这个用来存储数据库管理对象
        self.kafka_manager = None  # Kafka管理器
        self.message_dispatcher = None  # 消息分发器
        self.admin_cli = None  # 管理员命令行接口

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
            self.args = self.tools.parse_args()

        else:

            class Args:
                listen_port = self.config.get_listen_port()
                broker = self.config.get_broker()

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
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)

    def _init_socket_server(self):
        """
        Initialize the socket server to listen for incoming connections from charging points.
        """

        try:

            if self.debug_mode:
                server_host = self.config.get_ip_port_ev_cp_central()[0]
                server_port = self.config.get_listen_port()
            else:
                server_host = "0.0.0.0"
                server_port = self.args.listen_port

            # 将自定义消息处理函数分配给 socket 服务器
            self.socket_server = MySocketServer(
                host=server_host,
                port=server_port,
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

    def _initialize_message_dispatcher(self):
        try:
            self.message_dispatcher = MessageDispatcher(
                logger=self.logger,
                db_manager=self.db_manager,
                socket_server=self.socket_server,
                kafka_manager=self.kafka_manager,
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize MessageDispatcher: {e}")
            sys.exit(1)
    
    def _handle_client_disconnect(self, client_id):
        """
        处理客户端断开连接

        该方法会尝试处理两种类型的客户端断开：
        1. 充电桩 (ChargingPoint/Monitor)
        2. 司机应用 (Driver)
        """
        self.logger.debug(f"Client {client_id} disconnected, identifying client type...")

        # 首先尝试作为Driver处理
        driver_id = self.message_dispatcher.handle_driver_disconnect(client_id)
        if driver_id:
            self.logger.warning(f"Driver {driver_id} (client {client_id}) disconnected")
            return

        # 如果不是Driver，尝试作为ChargingPoint处理
        cp_id = self.message_dispatcher.charging_point_manager.handle_client_disconnect(
            client_id
        )
        if cp_id:
            self.logger.info(f"ChargingPoint {cp_id} (client {client_id}) disconnected")
            self.logger.info(f"Charging point {cp_id} status set to DISCONNECTED")
            return

        # 如果既不是Driver也不是ChargingPoint
        self.logger.warning(f"Unknown client type {client_id} disconnected")

    def _process_charging_point_message(self, client_id, message):
        """
        作为消息的分发中心。根据消息的 'type' 字段，调用相应的处理方法。
        """

        return self.message_dispatcher.dispatch_message(client_id, message)

    def _init_kafka_producer(self):
        """初始化Kafka生产者"""
        self.logger.debug("Initializing Kafka producer")
        broker_address = f"{self.args.broker[0]}:{self.args.broker[1]}"
        try:
            self.kafka_manager = KafkaManager(broker_address, self.logger)

            if self.kafka_manager.init_producer():
                # 创建Central需要的所有Kafka topics
                self.logger.debug("Creating required Kafka topics...")

                # 充电会话相关topics（Engine -> Central）
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.CHARGING_SESSION_DATA,
                    num_partitions=3,
                    replication_factor=1
                )
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.CHARGING_SESSION_COMPLETE,
                    num_partitions=1,
                    replication_factor=1
                )

                # Driver请求相关topics（Driver -> Central）
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.DRIVER_CHARGE_REQUESTS,
                    num_partitions=3,
                    replication_factor=1
                )
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.DRIVER_STOP_REQUESTS,
                    num_partitions=3,
                    replication_factor=1
                )
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.DRIVER_CPS_REQUESTS,
                    num_partitions=3,
                    replication_factor=1
                )

                # 创建统一的Driver响应主题（所有Driver共享）
                # 通过消息中的driver_id字段区分不同Driver
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.DRIVER_RESPONSES,
                    num_partitions=3,  # 多分区支持更好的并发性能
                    replication_factor=1
                )

                self.logger.debug("Kafka producer initialized successfully")
                return True
            else:
                self.logger.error("Failed to initialize Kafka producer")
                return False
        except Exception as e:
            self.logger.error(f"Error initializing Kafka producer: {e}")
            return False

    def _init_kafka_consumer(self):
        """初始化Kafka消费者（订阅Engine和Driver发送的消息）"""
        self.logger.debug("Initializing Kafka consumer")
        try:
            if not self.kafka_manager:
                self.logger.error("Kafka manager not initialized")
                return False

            # 启动Kafka管理器
            self.kafka_manager.start()

            # 订阅充电数据主题（来自Engine）
            success1 = self.kafka_manager.subscribe_topic(
                KafkaTopics.CHARGING_SESSION_DATA,
                self._handle_charging_data_from_kafka,
                group_id="central_charging_data_group",
            )

            # 订阅充电完成主题（来自Engine）
            success2 = self.kafka_manager.subscribe_topic(
                KafkaTopics.CHARGING_SESSION_COMPLETE,
                self._handle_charging_complete_from_kafka,
                group_id="central_charging_complete_group",
            )

            # 订阅Driver充电请求主题
            success3 = self.kafka_manager.subscribe_topic(
                KafkaTopics.DRIVER_CHARGE_REQUESTS,
                self._handle_driver_request_from_kafka,
                group_id="central_driver_requests_group",
            )

            # 订阅Driver停止充电请求主题
            success4 = self.kafka_manager.subscribe_topic(
                KafkaTopics.DRIVER_STOP_REQUESTS,
                self._handle_driver_request_from_kafka,
                group_id="central_driver_stop_group",
            )

            # 订阅Driver查询可用充电桩请求主题
            success5 = self.kafka_manager.subscribe_topic(
                KafkaTopics.DRIVER_CPS_REQUESTS,
                self._handle_driver_request_from_kafka,
                group_id="central_driver_cps_group",
            )

            if success1 and success2 and success3 and success4 and success5:
                self.logger.debug(
                    "Kafka consumers initialized successfully (charging_session_data, charging_session_complete, driver_requests)"
                )
                return True
            else:
                self.logger.error("Failed to initialize some Kafka consumers")
                return False

        except Exception as e:
            self.logger.error(f"Error initializing Kafka consumer: {e}")
            return False

    def _handle_charging_data_from_kafka(self, message):
        """处理来自Kafka的充电数据（由Engine发送）"""
        try:
            self.logger.debug(f"Received charging data from Kafka: {message}")

            # 委托给 MessageDispatcher 处理
            if self.message_dispatcher:
                self.message_dispatcher.dispatch_message("Kafka", message)
            else:
                self.logger.warning(
                    "MessageDispatcher not initialized, cannot process Kafka message"
                )

        except Exception as e:
            self.logger.error(f"Error handling charging data from Kafka: {e}")

    def _handle_charging_complete_from_kafka(self, message):
        """处理来自Kafka的充电完成消息（由Engine发送）"""
        try:
            self.logger.debug(f"Received charging completion from Kafka: {message}")

            # 委托给 MessageDispatcher 处理
            if self.message_dispatcher:
                self.message_dispatcher.dispatch_message("Kafka", message)
            else:
                self.logger.warning(
                    "MessageDispatcher not initialized, cannot process Kafka message"
                )

        except Exception as e:
            self.logger.error(f"Error handling charging completion from Kafka: {e}")

    def _handle_driver_request_from_kafka(self, message):
        """处理来自Kafka的Driver请求（充电请求、停止请求、查询可用充电桩）"""
        try:
            msg_type = message.get("type", "unknown")
            driver_id = message.get("driver_id", "unknown")
            self.logger.debug(f"Received Driver request from Kafka: type={msg_type}, driver_id={driver_id}")

            # 委托给 MessageDispatcher 处理
            # 注意：由于Driver不再通过Socket连接，我们需要使用driver_id作为client_id
            if self.message_dispatcher:
                self.message_dispatcher.dispatch_message(driver_id, message)
            else:
                self.logger.warning(
                    "MessageDispatcher not initialized, cannot process Kafka message"
                )

        except Exception as e:
            self.logger.error(f"Error handling Driver request from Kafka: {e}")

    def initialize_systems(self):
        self.logger.debug("Initializing systems...")
        self._init_socket_server()

        self._init_database()

        # 先初始化Kafka（这样MessageDispatcher可以使用它）
        if self._init_kafka_producer():
            # MessageDispatcher需要kafka_manager，所以在这里初始化
            self._initialize_message_dispatcher()
            self._init_kafka_consumer()
        else:
            self.logger.warning(
                "Kafka initialization failed, continuing without Kafka support"
            )
            # 即使Kafka失败，也需要初始化MessageDispatcher（用于Socket通信）
            self._initialize_message_dispatcher()

        # 初始化管理员CLI
        self._init_admin_cli()

        self.logger.info("All systems initialized successfully.")

    def _init_admin_cli(self):
        """初始化管理员命令行接口"""
        try:
            self.admin_cli = AdminCLI(self)
            self.admin_cli.start()
            self.logger.debug("Admin CLI initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Admin CLI: {e}")
            # 不要因为CLI失败而退出系统
            self.admin_cli = None

    def shutdown_systems(self):
        self.logger.debug("Shutting down systems...")
        
        # 在停止Kafka之前，向所有Driver发送connection_error消息
        if self.message_dispatcher:
            try:
                self.message_dispatcher.notify_all_drivers_connection_error()
            except Exception as e:
                self.logger.error(f"Error notifying drivers about shutdown: {e}")
        
        if self.admin_cli:
            self.admin_cli.stop()
        if self.socket_server:
            self.socket_server.stop()
        if self.kafka_manager:
            self.kafka_manager.stop()
        self.running = False

    def start(self):
        # self.logger.debug(
        #     f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        # )

        self.initialize_systems()


if __name__ == "__main__":
    import logging
    config = ConfigManager()
    debug_mode = config.get_debug_mode()
    if not debug_mode:
        logger = CustomLogger.get_logger(level=logging.INFO)
    else:
        logger = CustomLogger.get_logger(level=logging.DEBUG)
    ev_central = EV_Central(logger=logger)

    try:
        ev_central.start()
        # ev_central.logger.info(
        #     "EV Central main process is now idling, waiting for KeyboardInterrupt or external stop signal."
        # )

        while ev_central.socket_server.running_event.is_set():
            time.sleep(0.1)

        ev_central.logger.info("EV Central main loop finished.")

    except KeyboardInterrupt:
        ev_central.logger.debug("Shutting down EV Central due to KeyboardInterrupt.")
    finally:
        ev_central.shutdown_systems()
        sys.exit(0)
