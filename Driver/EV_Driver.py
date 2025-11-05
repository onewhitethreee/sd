"""
Aplicación que usan los consumidores para usar los puntos de recarga
"""

import sys
import os
import time
import uuid
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from Common.Config.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.Config.CustomLogger import CustomLogger
from Common.Config.ConfigManager import ConfigManager
from Common.Queue.KafkaManager import KafkaManager, KafkaTopics
from Driver.DriverMessageDispatcher import DriverMessageDispatcher
from Driver.DriverCLI import DriverCLI
from Common.Message.MessageTypes import MessageTypes

class Driver:
    def __init__(self, logger=None):
        """
        Inicializa el Driver
        """
        self.logger = logger
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()

        if not self.debug_mode:
            self.tools = AppArgumentParser(
                "Driver", "Aplicación del conductor para usar puntos de recarga"
            )
            self.tools.add_argument(
                "broker",
                type=ip_port_type,
                help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)",
            )
            self.tools.add_argument(
                "id_client", type=str, help="Identificador único del cliente"
            )
            self.args = self.tools.parse_args()
        else:

            class Args:
                broker = self.config.get_broker()
                import random
                id_client = f"driver_{random.randint(0,99999)}"

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        self.kafka_manager = None 
        self.driver_cli = None  
        self.running = False

        # session info
        self.current_charging_session = None  

        # cache session info
        self.available_charging_points = []  
        self.available_cps_cache_time = None  

        self.service_queue = []

        self.lock = threading.Lock()  
        self.message_dispatcher = DriverMessageDispatcher(
            self.logger, self
        )  

    def _send_charge_request(self, cp_id):
        """
        Enviar solicitud de carga a queue que sera producido por central
        """
        request_message = {
            "type": MessageTypes.CHARGE_REQUEST,
            "message_id": str(uuid.uuid4()),
            "cp_id": cp_id,
            "driver_id": self.args.id_client,
            "timestamp": int(time.time()),
        }

        self.logger.info(f"🚗 Sending charging request for CP: {cp_id}")

        # 发送到 Kafka
        if self.kafka_manager and self.kafka_manager.is_connected():
            kafka_success = self.kafka_manager.produce_message(
                KafkaTopics.DRIVER_CHARGE_REQUESTS, request_message
            )
            if kafka_success:
                self.logger.debug(f"Charge request sent to Kafka: {request_message['message_id']}")
            else:
                self.logger.error("Failed to send charge request to Kafka")
            return kafka_success
        else:
            self.logger.error("Kafka not connected, cannot send charge request")
            return False

    def _send_stop_charging_request(self):
        """
        Enviar solicitud de detención de carga a queue que sera producido por central
        """
        with self.lock:
            if not self.current_charging_session:
                self.logger.warning("No active charging session to stop")
                return False

            session_id = self.current_charging_session["session_id"]
            cp_id = self.current_charging_session["cp_id"]

        request_message = {
            "type": MessageTypes.STOP_CHARGING_REQUEST,
            "message_id": str(uuid.uuid4()),
            "session_id": session_id,
            "cp_id": cp_id,
            "driver_id": self.args.id_client,
            "timestamp": int(time.time()),
        }

        self.logger.info(f"🛑 Sending stop charging request for session: {session_id}")

        # 发送到 Kafka
        if self.kafka_manager and self.kafka_manager.is_connected():
            kafka_success = self.kafka_manager.produce_message(
                KafkaTopics.DRIVER_STOP_REQUESTS, request_message
            )
            if kafka_success:
                self.logger.debug(f"Stop request sent to Kafka: {request_message['message_id']}")
            else:
                self.logger.error("Failed to send stop request to Kafka")
            return kafka_success
        else:
            self.logger.error("Kafka not connected, cannot send stop request")
            return False

    def _request_available_cps(self):
        """
        Enviar solicitud de puntos de recarga disponibles
        """
        request_message = {
            "type": MessageTypes.AVAILABLE_CPS_REQUEST,
            "message_id": str(uuid.uuid4()),
            "driver_id": self.args.id_client,
            "timestamp": int(time.time()),
        }

        # 发送到 Kafka
        if self.kafka_manager and self.kafka_manager.is_connected():
            kafka_success = self.kafka_manager.produce_message(
                KafkaTopics.DRIVER_CPS_REQUESTS, request_message
            )
            if kafka_success:
                self.logger.debug(f"Available CPs request sent to Kafka: {request_message['message_id']}")
            else:
                self.logger.error("Failed to send available CPs request to Kafka")
            return kafka_success
        else:
            self.logger.error("Kafka not connected, cannot request available CPs")
            return False

    def _request_charging_history(self):
        """
        Consultar el historial de carga

        Returns:
            bool: si la solicitud fue enviada con éxito
        """
        request_message = {
            "type": MessageTypes.CHARGING_HISTORY_REQUEST,
            "message_id": str(uuid.uuid4()),
            "driver_id": self.args.id_client,
            "timestamp": int(time.time()),
        }

        # 发送查询请求到 Kafka
        if self.kafka_manager and self.kafka_manager.is_connected():
            kafka_success = self.kafka_manager.produce_message(
                KafkaTopics.DRIVER_CPS_REQUESTS,  # 使用请求主题
                request_message
            )
            if kafka_success:
                self.logger.debug(f"Charging history request sent to Kafka: {request_message['message_id']}")
            else:
                self.logger.error("Failed to send charging history request to Kafka")
            return kafka_success
        else:
            self.logger.error("Kafka not connected, cannot request charging history")
            return False

    def _load_services_from_file(self, filename="test_services.txt"):
        """
        Requisito que pidio por el enunciado: cargar servicios desde un archivo de texto
        """
        try:
            if not os.path.exists(filename):
                self.logger.warning(f"Service file {filename} not found")
                return []

            with open(filename, "r") as f:
                services = [line.strip() for line in f if line.strip()]

            self.logger.info(f"Loaded {len(services)} services from {filename}")
            return services
        except Exception as e:
            self.logger.error(f"Error loading services from file: {e}")
            return []

    def _formatter_charging_points(self, charging_points):
        """
        Formatear y mostrar la lista de puntos de carga disponibles
        Args:
            charging_points: Lista de puntos de carga
        """
        for i, cp in enumerate(charging_points, 1):
            print(f"[{i}] charging point {cp['id']}")
            print(f"    ├─ Location: {cp['location']}")
            print(f"    ├─ Price/kWh: €{cp['price_per_kwh']}/kWh")
            print(f"    ├─ Status: {cp['status']}")
            print()

    def _show_charging_history(self, history_data=None):
        """
        Mostrar el historial de carga

        Args:
            history_data: lista de datos del historial de carga. Si no se proporciona, se iniciará una solicitud de consulta
        """
        if history_data is None:
            self.logger.info("Requesting charging history from Central...")
            # 发起查询请求，响应会异步到达并由 DriverMessageDispatcher 处理
            self._request_charging_history()
            return

        if not history_data:
            self.logger.info("No charging history available")
            return
        self._formatter_history_data(history_data)

    def _formatter_history_data(self, history_data):
        """
        Formatear y mostrar los datos del historial de carga
        Args:
            history_data: lista de datos del historial de carga
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("Charging History")
        self.logger.info("=" * 60)
        for i, record in enumerate(history_data, 1):
            self.logger.info(f"\n[{i}] Session: {record.get('session_id', 'N/A')}")
            self.logger.info(f"    CP ID: {record.get('cp_id', 'N/A')}")
            self.logger.info(f"    Start Time: {record.get('start_time', 'N/A')}")
            self.logger.info(f"    End Time: {record.get('end_time', 'N/A')}")
            self.logger.info(
                f"    Energy: {record.get('energy_consumed_kwh', 0):.3f}kWh"
            )
            self.logger.info(f"    Cost: €{record.get('total_cost', 0):.2f}")
        self.logger.info("=" * 60 + "\n")
    def _process_next_service(self):
        """
        procesar el siguiente servicio desde el fichero de prueba
        """
        
        if self.service_queue:
            cp_id = self.service_queue.pop(0)
            self.logger.info(f"Processing next service: {cp_id}")
            self._send_charge_request(cp_id)
        else:
            self.logger.info("No more services to process")
            # 查询并显示充电历史（异步，响应会通过 Kafka 返回）
            self._request_charging_history()

    def _auto_mode(self, services):
        
        self.logger.info(f"Entering auto mode with {len(services)} services")
        print(f"🤖 Auto mode: Processing {len(services)} charging point(s) automatically")
        print(f"    Type 'help' to see available commands during auto mode\n")

        self.service_queue = services.copy()

        # 处理第一个服务
        if self.service_queue:
            self._process_next_service()

        # 等待所有服务完成
        # CLI在后台运行，用户可以随时输入命令
        while self.running and (self.service_queue or self.current_charging_session):
            time.sleep(1)

    def _init_kafka(self):
        """
        Inicializar Kafka
        """
        broker_address = f"{self.args.broker[0]}:{self.args.broker[1]}"

        try:
            self.kafka_manager = KafkaManager(broker_address, self.logger)

            if self.kafka_manager.init_producer():
                self.kafka_manager.start()

                # 创建Driver相关的topics
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
                # 创建统一的Driver响应主题（所有Driver共享一个主题）
                driver_response_topic = KafkaTopics.get_driver_response_topic()
                self.kafka_manager.create_topic_if_not_exists(
                    driver_response_topic,
                    num_partitions=3,  
                    replication_factor=1
                )

                # 订阅统一的Driver响应主题
                # 重要：每个Driver使用独立的consumer group，确保每个Driver都能收到属于自己的消息
                # 应用层通过 driver_id 字段过滤消息
                self.kafka_manager.init_consumer(
                    driver_response_topic,
                    f"driver_{self.args.id_client}_consumer_group",  # 每个Driver独立的consumer group
                    self._handle_kafka_message,
                )

                self.logger.info("Kafka producer initialized successfully")
                self.logger.info(f"Subscribed to unified response topic: {driver_response_topic} with driver_id filter: {self.args.id_client}")
                return True
            else:
                self.logger.error("Failed to initialize Kafka producer")
                return False

        except Exception as e:
            self.logger.error(f"Error initializing Kafka: {e}")
            return False

    def _handle_kafka_message(self, message):
        """
        Maneja los mensajes recibidos desde Kafka
        Args:
            message: Mensaje recibido desde Kafka
        """
        try:
            msg_type = message.get("type")
            message_driver_id = message.get("driver_id")

            # 应用层过滤：只处理属于当前Driver的消息
            # 由于使用统一的响应主题，需要检查消息中的driver_id字段
            if message_driver_id != self.args.id_client:
                # 消息不属于当前Driver，忽略（这在正常情况下不应该发生，因为consumer group机制）
                self.logger.debug(
                    f"Ignoring message for different driver: message_driver_id={message_driver_id}, "
                    f"current_driver_id={self.args.id_client}"
                )
                return

            self.logger.debug(
                f"Received Kafka message from unified topic: type={msg_type}, driver_id={message_driver_id}"
            )

            # 使用消息分发器处理Kafka消息
            # DriverMessageDispatcher 会处理以下类型：
            # - charge_request_response: 充电请求响应
            # - stop_charging_response: 停止充电响应
            # - available_cps_response: 可用充电桩列表响应
            # - charging_status_update: 充电状态更新
            # - charging_data: 实时充电数据
            # - charge_completion: 充电完成通知
            self.message_dispatcher.dispatch_message(message)

        except Exception as e:
            self.logger.error(f"Error handling Kafka message: {e}", exc_info=True)

    def start(self):
        """启动Driver应用"""
        self.logger.info(f"Starting Driver module")
        self.logger.info(
            f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )
        self.logger.info(f"Driver ID: {self.args.id_client}")

        self.running = True

        if not self._init_kafka():
            self.logger.error("Failed to initialize Kafka. Cannot start Driver.")
            print("\n❌ Failed to connect to Kafka Broker. Please ensure Kafka is running and try again.\n")
            self.running = False
            return

        # 请求可用充电点列表
        self._request_available_cps()
        time.sleep(2)

        # 🔧 关键改动：提前启动CLI，使其在任何模式下都可用
        self._init_cli()

        # 检查是否有服务文件
        services = self._load_services_from_file()

        try:
            if services:
                self._auto_mode(services)
            else:
                # 交互模式（CLI已在后台运行）
                # 只需要等待CLI运行即可
                self.logger.info("Entering interactive mode...")
                print("💬 Interactive mode: Enter commands to control charging")
                print("    Type 'help' to see available commands\n")

                while self.running and self.driver_cli and self.driver_cli.running:
                    time.sleep(0.1)

        except KeyboardInterrupt:
            self.logger.info("Shutting down Driver")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
        finally:
            self.running = False
            if self.driver_cli:
                self.driver_cli.stop()
            if self.kafka_manager:
                self.kafka_manager.stop()

    def _init_cli(self):
        """
        Inicializar el CLI del Driver
        """
        try:
            self.driver_cli = DriverCLI(self)
            self.driver_cli.start()
            self.logger.info("Driver CLI initialized and started")
        except Exception as e:
            self.logger.error(f"Failed to initialize Driver CLI: {e}")
            self.driver_cli = None


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    driver = Driver(logger=logger)
    driver.start()
