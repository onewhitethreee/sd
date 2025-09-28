"""
Módulo que representa la central de control de toda la solución. Implementa la lógica y gobierno de todo el sistema.
"""

import sys
import os
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.SqliteConnection import SqliteConnection
from Common.MessageFormatter import MessageFormatter
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager
from Common.MySockerServer import MySocketServer


class EV_Central:
    def __init__(self, logger=None):
        self.logger = logger
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()
        self.socket_server = None
        self._registered_charging_points = {}
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
                broker = self.config.get_broker()
                db = self.config.get_db()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        self.db_manager = None # 这个用来存储数据库管理对象
        self.db_path = self.config.get_db_path()
        self.sql_schema = os.path.join("Core", "BD", "table.sql")
        self.charging_points = {}

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
                message_callback=self._process_charging_point_message
            )
            # 通过MySocketServer类的start方法启动服务器
            self.socket_server.start()
            self.logger.debug("Socket server initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize socket server: {e}")
            sys.exit(1)

    def _process_charging_point_message(self, client_id, message):
        """
        作为消息的分发中心。根据消息的 'type' 字段，调用相应的处理方法。
        """
        self.logger.info(f"收到来自客户端 {client_id} 的消息: {message}")

        msg_type = message.get("type")

        if msg_type.lower() == "register":
            # 如果是注册消息，就交给注册专员处理
            return self._handle_register_message(client_id, message)

        # elif msg_type == "heartbeat":
        #     # 未来可以在这里添加对心跳消息的处理
        #     pass

        # elif msg_type == "status_update":
        #     # 未来可以在这里添加对状态更新消息的处理
        #     pass

        else:
            # 如果是未知类型的消息，返回一个错误信息
            self.logger.warning(f"收到来自 {client_id} 的未知消息类型: '{msg_type}'")
            return MessageFormatter.create_response_message(
                cp_type=msg_type,
                message_id=message.get("message_id", ""),
                status="failure",
                info=f"未知的消息类型: '{msg_type}'",
            )

    def _handle_register_message(self, client_id, message): # TODO: review
        """
        专门处理充电桩的注册请求。
        """
        self.logger.info(f"正在处理来自 {client_id} 的注册请求...")

        cp_id = message.get("id")
        location = message.get("location")
        price_per_kwh = message.get("price_per_kwh")

        # 检查必要字段是否存在
        # TODO 是否需要另外添加message_id的检查?
        if not all([cp_id, location, price_per_kwh]):
            self.logger.error(f"注册消息缺少必要字段: {message}")
            return MessageFormatter.create_response_message(
                message_id=message.get("message_id", ""),
                status="failure",
                info="注册消息中缺少必要字段"
            )
        # 插入数据库
        try:
            self.logger.debug(f"尝试将充电桩 {cp_id} 注册到数据库...")
            self.db_manager.insert_or_update_charging_point(
                cp_id=cp_id,
                location=location,
                price_per_kwh=price_per_kwh,
                status="active",
                last_connection_time=None,
            )
            self.logger.info(f"充电桩 {cp_id} 注册成功！")
        except Exception as e:
            self.logger.debug(f"注册充电桩 {cp_id} 失败: {e}")
            return MessageFormatter.create_response_message(
                cp_type="register",
                message_id=message.get("message_id", ""),
                status="failure",
                info=f"注册失败: {e}"
            )
        # 更新内存中的注册列表
        self._registered_charging_points[cp_id] = {
            "client_id": client_id,
            "location": location,
            "price_per_kwh": price_per_kwh,
            "status": "active",
            "last_connection_time": None,
        }

        self._debug_print_registered_charging_points()

        return MessageFormatter.create_response_message(
            cp_type="register",
            message_id=message.get("message_id", ""),
            status="success",
            info=f"charging point {cp_id} registered successfully."
        )
    
    def _debug_print_registered_charging_points(self):
        if self.debug_mode:
            self.logger.debug("当前注册的充电桩:")
            for cp_id, details in self._registered_charging_points.items():
                self.logger.debug(f" - {cp_id}: {details}")
    
    def _handle_heartbeat_message(self, client_id, message): # TODO: implement
        """
        处理充电桩发送的心跳消息，更新其最后连接时间。
        这个函数是用来检测充电桩是否在线的。要求每30秒发送一次心跳消息。
        """
        pass

    def get_all_registered_charging_points(self):
        """
        Retrieve all registered charging points from the database.
        Returns a list of dictionaries with charging point details.
        """
        if not self.db_manager:
            self.logger.error("Database connection is not initialized.")
            return []

        return SqliteConnection.get_all_charging_points(self.db_manager)

    def _init_kafka_producer(self): # TODO: implement
        self.logger.debug("Initializing Kafka producer")
        pass

    def _init_kafka_consumer(self): # TODO: implement
        self.logger.debug("Initializing Kafka consumer")
        pass

    def initialize_systems(self):
        self.logger.info("Initializing systems...")
        self._init_database()
        self._init_socket_server()
        print(self.get_all_registered_charging_points())
        # self._init_kafka_producer()
        # self._init_kafka_consumer()
        self.logger.info("All systems initialized successfully.")

    def shutdown_systems(self):
        self.logger.info("Shutting down systems...")
        if self.socket_server:
            self.socket_server.stop()
        if self.db_manager:
            self.db_manager.close_connection()

    def start(self):
        self.logger.debug(f"Starting EV Central on port {self.args.listen_port}")
        self.logger.debug(
            f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )
        self.logger.debug(
            f"Connecting to Database at {self.args.db[0]}:{self.args.db[1]}"
        )

        self.initialize_systems()

        try:
            ## SOCKET HERE ##
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            self.logger.info("Shutting down EV Central")
            self.shutdown_systems()
            sys.exit(0)


if __name__ == "__main__":

    logger = CustomLogger.get_logger()
    ev_central = EV_Central(logger=logger)
    ev_central.start()

# TODO 检查一下发送消息，有一个错误需要修复
# TODO 再解决如果用户发送少了属性服务器也要返回相对的错误信息给用户
