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
from Common.Status import Status

class EV_Central:
    def __init__(self, logger=None):
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()

        self.logger = logger
        self.socket_server = None
        self._registered_charging_points = {}
        self.db_manager = None  # 这个用来存储数据库管理对象
        self.db_path = self.config.get_db_path()
        self.sql_schema = os.path.join("Core", "BD", "table.sql")
        self.running = False

        if not self.debug_mode:
            self.tools = AppArgumentParser(
                app_name="EV_Central",
                app_description="Sistema Central de Control para Puntos de Recarga de Vehículos Eléctricos",
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
            # 读取所有已注册的充电桩到内存中
            # TODO 在没有与charging point 连接的情况下，充电桩的状态都是disconnected， 这里需要改进
            for cp in self.get_all_registered_charging_points():
                # 系统启动时，所有充电桩都设置为离线状态
                cp_data = {
                    "id": cp["id"],
                    "location": cp["location"],
                    "price_per_kwh": cp["price_per_kwh"],
                    "status": Status.DISCONNECTED.value,  # 统一设置为离线
                    "last_connection_time": cp["last_connection_time"],
                    # "client_id": None  # 还没有客户端连接
                }
                self._registered_charging_points[cp["id"]] = cp_data
                
                # 更新数据库中的状态为 DISCONNECTED
                self.db_manager.update_charging_point_status(
                    cp_id=cp["id"],
                    status=Status.DISCONNECTED.value
                )
                
            self.logger.info(f"Loaded {len(self._registered_charging_points)} charging points from database")
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)

    def _init_socket_server(self):
        """
        Initialize the socket server to listen for incoming connections from charging points.
        """
        self.logger.debug("Initializing socket server")
        self._cp_connections = {}  # {cp_id: client_socket}
        self._client_to_cp = {}  # {client_id: cp_id}
        try:

            # 将自定义消息处理函数分配给 socket 服务器
            self.socket_server = MySocketServer(
                host=self.config.get_ip_port_ev_cp_central()[0],
                port=self.config.get_ip_port_ev_cp_central()[1],
                logger=self.logger,
                message_callback=self._process_charging_point_message,
            )
            # 通过MySocketServer类的start方法启动服务器
            self.socket_server.start()
            self.running = True
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

        handlers = {
            "register_request": self._handle_register_message,
            "heartbeat_request": self._handle_heartbeat_message,
            # "charge_completion": self._handle_charging_completion,
            # "status_update": self._handle_status_update,
            # TODO 添加其他消息类型的处理函数
        }

        handler = handlers.get(msg_type)
        if handler:
            return handler(client_id, message)
        else:
            self.logger.error(f"Unknown message type from {client_id}: '{msg_type}'")
            return MessageFormatter.create_response_message(
                cp_type=f"{msg_type}_response",
                message_id=message.get("message_id", ""),
                status="failure",
                info=f"Unknown message type: '{msg_type}'",
            )

    def _handle_register_message(self, client_id, message):  # TODO: review
        """
        专门处理充电桩的注册请求。
        """
        self.logger.info(f"正在处理来自 {client_id} 的注册请求...")

        cp_id = message.get("id")
        location = message.get("location")
        price_per_kwh = message.get("price_per_kwh")
        message_id = message.get("message_id")

        if not message_id:
            return MessageFormatter.create_response_message(
                cp_type="register_response",
                message_id="",
                status="failure",
                info="注册消息中缺少 message_id 字段",
            )

        missing_fields = []
        if not cp_id:
            missing_fields.append("id")
        if not location:
            missing_fields.append("location")
        if price_per_kwh is None:
            missing_fields.append("price_per_kwh")
        if missing_fields:
            return MessageFormatter.create_response_message(
                cp_type="register_response",
                message_id=message_id,
                status="failure",
                info=f"注册消息中缺少字段: {', '.join(missing_fields)}",
            )

        # 插入数据库
        try:
            price_per_kwh = float(price_per_kwh)
            if price_per_kwh < 0:
                raise ValueError("price_per_kwh must be non-negative")

            self.logger.debug(f"尝试将充电桩 {cp_id} 注册到数据库...")
            self.db_manager.insert_or_update_charging_point(
                cp_id=cp_id,
                location=location,
                price_per_kwh=price_per_kwh,
                status=Status.DISCONNECTED.value,  # 初始状态为 DISCONNECTED，等待心跳消息更新
                last_connection_time=None,
            )
            self.logger.info(f"充电桩 {cp_id} 注册成功！")
        except Exception as e:
            self.logger.debug(f"注册充电桩 {cp_id} 失败: {e}")
            return MessageFormatter.create_response_message(
                cp_type="register_response",
                message_id=message_id,
                status="failure",
                info=f"注册失败: {e}",
            )

        # 维护连接映射
        self._cp_connections[cp_id] = client_id
        self._client_to_cp[client_id] = cp_id

        # 更新内存中的注册列表
        self._registered_charging_points[cp_id] = {
            "client_id": client_id,
            "location": location,
            "price_per_kwh": price_per_kwh,
            "status": Status.DISCONNECTED.value,  # 初始状态为 DISCONNECTED，等待心跳消息更新
            "last_connection_time": None,
        }

        # 调试输出当前所有注册的充电桩
        self._debug_print_registered_charging_points()

        return MessageFormatter.create_response_message(
            cp_type="register_response",
            message_id=message.get("message_id", ""),
            status="success",
            info=f"charging point {cp_id} registered successfully.",
        )

    def _handle_authorization_message(
        self, cp_id, client_id, message
    ):  # TODO: implement
        """
        处理来自司机应用程序或充电点本身的充电授权请求。
        需要验证充电点是否可用，并决定是否授权。
        成功授权后，需要向充电点和司机应用程序发送授权通知。
        """
        pass

    def _handle_charging_data_message(self, client_id, message):  # TODO: implement
        """
        处理充电点在充电过程中实时发送的电量消耗和费用信息。
        这些数据需要更新到内部状态和数据库，并显示在监控面板上。
        """
        pass

    def _handle_fault_notification_message(self, client_id, message):  # TODO: implement
        """
        处理充电点发送的故障或异常通知。
        需要记录这些事件，并可能触发警报或通知维护人员。
        """
        pass

    def _handle_recovery_message(self, client_id, message):  # TODO: implement
        """
        处理充电点在故障修复后发送的恢复通知。
        需要更新其状态，并可能重新启用其服务。
        """
        pass

    def _handle_heartbeat_message(self, client_id, message):  # TODO: implement
        """
        处理充电桩发送的心跳消息，更新其最后连接时间。
        这个函数是用来检测充电桩是否在线的。要求每30秒发送一次心跳消息。
        """
        self.logger.info(f"Processing heartbeat from client {client_id}")
        cp_id = message.get("id")
        if not cp_id:
            return MessageFormatter.create_response_message(
                cp_type="heartbeat_response",
                message_id=message.get("message_id", ""),
                status="failure",
                info="心跳消息中缺少 id 字段",
            )
        current_time = datetime.now(timezone.utc).isoformat()
        if cp_id in self._registered_charging_points:
            self._registered_charging_points[cp_id][
                "last_connection_time"
            ] = current_time
            # 同步更新数据库中的最后连接时间
            try:
                self.db_manager.insert_or_update_charging_point(
                    cp_id=cp_id,
                    location=self._registered_charging_points[cp_id]["location"],
                    price_per_kwh=self._registered_charging_points[cp_id][
                        "price_per_kwh"
                    ],
                    status=Status.ACTIVE.value,  # 心跳消息表示充电桩在线，更新状态为 ACTIVE
                    last_connection_time=current_time,
                )
                self._show_registered_charging_points()
                return MessageFormatter.create_response_message(
                    cp_type="heartbeat_response",
                    message_id=message.get("message_id", ""),
                    status="success",
                    info="Heartbeat received and last connection time updated.",
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to update last connection time for {cp_id}: {e}"
                )
                return MessageFormatter.create_response_message(
                    cp_type="heartbeat_response",
                    message_id=message.get("message_id", ""),
                    status="failure",
                    info=f"Failed to update last connection time: {e}",
                )
        else:
            self.logger.warning(
                f"Received heartbeat from unregistered charging point {cp_id}"
            )
            return MessageFormatter.create_response_message(
                cp_type="heartbeat_response",
                message_id=message.get("message_id", ""),
                status="failure",
                info=f"Charging point {cp_id} is not registered.",
            )

    def _handle_manual_command(self, cp_id, command):  # TODO: implement
        """
        处理来自管理员的手动命令，如启动或停止充电点。
        这些命令需要通过消息队列发送到相应的充电点。
        """
        pass

    def _debug_print_registered_charging_points(self):
        if self.debug_mode:
            self.logger.debug("当前注册的充电桩:")
            for cp_id, details in self._registered_charging_points.items():
                self.logger.debug(f" - {cp_id}: {details}")

    def _generate_unique_message_id(self):
        """
        生成一个唯一的消息ID，使用UUID
        """
        import uuid

        return str(uuid.uuid4())

    def _show_registered_charging_points(self):
        """
        打印所有已注册的充电桩及其状态。
        """
        if not self._registered_charging_points:
            print("\n>>> No hay puntos de recarga registrados\n")
            return

        print("\n" + "╔" + "═"*60 + "╗")
        print("║" + " Puntos de recarga registrados ".center(60) + "║")
        print("╚" + "═"*60 + "╝\n")
        
        for i, (cp_id, details) in enumerate(self._registered_charging_points.items(), 1):
            print(f"【{i}】 charging point {cp_id}")
            print(f"    ├─ Location: {details['location']}")
            print(f"    ├─ Price/kWh: €{details['price_per_kwh']}/kWh")
            print(f"    ├─ Status: {details['status']}")
            print(f"    └─ Last Connection: {details['last_connection_time']}")
            print()


    def get_all_registered_charging_points(self):
        """
        Retrieve all registered charging points from the database.
        Returns a list of dictionaries with charging point details.
        """
        if not self.db_manager:
            self.logger.error("Database connection is not initialized.")
            return []

        return self.db_manager.get_all_charging_points()

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
        self._show_registered_charging_points()

    def shutdown_systems(self):
        self.logger.info("Shutting down systems...")
        if self.socket_server:
            self.socket_server.stop()
        if self.db_manager:
            self.db_manager.close_connection()
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
        try:
            ## SOCKET HERE ##
            while self.running:
                pass  # TODO 这里在部署的时候不能用死循环，需要改成非阻塞的方式
        except KeyboardInterrupt:
            self.logger.info("Shutting down EV Central")
            self.shutdown_systems()
            sys.exit(0)


if __name__ == "__main__":

    logger = CustomLogger.get_logger()
    ev_central = EV_Central(logger=logger)
    ev_central.start()

# TODO 解决如果用户发送少了属性服务器也要返回相对的错误信息给用户
# TODO 关闭服务器时，所有连接的充电桩都要被设置为离线状态