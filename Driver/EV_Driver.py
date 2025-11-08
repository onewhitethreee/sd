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
from Common.Config.ConsolePrinter import get_printer


class Driver:
    def __init__(self, logger=None):
        """
        Inicializa el Driver
        """
        self.logger = logger
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()
        self.printer = get_printer()  

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
        self.loaded_services = [] 

        self.lock = threading.Lock()
        self.message_dispatcher = DriverMessageDispatcher(self.logger, self)

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

        # Send to Kafka
        if self.kafka_manager and self.kafka_manager.is_connected():
            kafka_success = self.kafka_manager.produce_message(
                KafkaTopics.DRIVER_CHARGE_REQUESTS, request_message
            )
            if kafka_success:
                self.logger.debug(
                    f"Charge request sent to Kafka: {request_message['message_id']}"
                )
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

        # Send to Kafka
        if self.kafka_manager and self.kafka_manager.is_connected():
            kafka_success = self.kafka_manager.produce_message(
                KafkaTopics.DRIVER_STOP_REQUESTS, request_message
            )
            if kafka_success:
                self.logger.debug(
                    f"Stop request sent to Kafka: {request_message['message_id']}"
                )
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

        # Send to Kafka
        if self.kafka_manager and self.kafka_manager.is_connected():
            kafka_success = self.kafka_manager.produce_message(
                KafkaTopics.DRIVER_CPS_REQUESTS, request_message
            )
            if kafka_success:
                self.logger.debug(
                    f"Available CPs request sent to Kafka: {request_message['message_id']}"
                )
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

        # Send query request to Kafka
        if self.kafka_manager and self.kafka_manager.is_connected():
            kafka_success = self.kafka_manager.produce_message(
                KafkaTopics.DRIVER_CPS_REQUESTS, request_message  # Use request topic
            )
            if kafka_success:
                self.logger.debug(
                    f"Charging history request sent to Kafka: {request_message['message_id']}"
                )
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

            self.logger.debug(f"Loaded {len(services)} services from {filename}")
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
        # 这个方法现在由DriverCLI使用美化表格显示
        # 保留这个方法以保持向后兼容，但实际显示由DriverCLI处理
        pass

    def _show_charging_history(self, history_data=None):
        """
        Mostrar el historial de carga

        Args:
            history_data: lista de datos del historial de carga. Si no se proporciona, se iniciará una solicitud de consulta
        """
        if history_data is None:
            self.printer.print_info("Requesting charging history from Central...")
            # Initiate query request, response will arrive asynchronously and be handled by DriverMessageDispatcher
            self._request_charging_history()
            return

        if not history_data:
            self.printer.print_warning("No charging history available")
            return
        self._formatter_history_data(history_data)

    def _formatter_history_data(self, history_data):
        """
        Formatear y mostrar los datos del historial de carga
        Args:
            history_data: lista de datos del historial de carga
        """
        if not history_data:
            self.printer.print_warning("No charging history available")
            return
        
        # 准备表格数据
        headers = ["#", "Session ID", "CP ID", "Start Time", "End Time", "Energy (kWh)", "Cost (€)"]
        rows = []
        
        for i, record in enumerate(history_data, 1):
            session_id = record.get('session_id', 'N/A')
            # 截断过长的session_id以便显示
            if len(session_id) > 20:
                session_id = session_id[:17] + "..."
            
            cp_id = record.get('cp_id', 'N/A')
            start_time = record.get('start_time', 'N/A')
            end_time = record.get('end_time', 'N/A')
            energy = record.get('energy_consumed_kwh', 0)
            cost = record.get('total_cost', 0)
            
            rows.append([
                str(i),
                session_id,
                cp_id,
                start_time,
                end_time,
                f"{energy:.3f}",
                f"€{cost:.2f}"
            ])
        
        # 使用美化表格显示
        title = f"Charging History (Total: {len(history_data)} records)"
        self.printer.print_table(title, headers, rows)

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
            # Query and display charging history (asynchronous, response will be returned via Kafka)
            self._request_charging_history()

    def _auto_mode(self, services):

        self.logger.debug(f"Entering auto mode with {len(services)} services")
        print(
            f"Processing {len(services)} charging point(s) from file automatically"
        )
        print(f"    Type 'help' to see available commands during auto mode\n")

        self.service_queue = services.copy()

        # Process the first service
        if self.service_queue:
            self._process_next_service()

        # Wait for all services to complete
        # CLI runs in the background, users can enter commands at any time
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

                # Create Driver-related topics
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.DRIVER_CHARGE_REQUESTS,
                    num_partitions=3,
                    replication_factor=1,
                )
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.DRIVER_STOP_REQUESTS,
                    num_partitions=3,
                    replication_factor=1,
                )
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.DRIVER_CPS_REQUESTS,
                    num_partitions=3,
                    replication_factor=1,
                )
                # Create unified Driver response topic (all Drivers share one topic)
                driver_response_topic = KafkaTopics.get_driver_response_topic()
                self.kafka_manager.create_topic_if_not_exists(
                    driver_response_topic, num_partitions=3, replication_factor=1
                )

                # Subscribe to unified Driver response topic
                # Important: Each Driver uses an independent consumer group, ensuring each Driver receives its own messages
                # Application layer filters messages by driver_id field
                self.kafka_manager.init_consumer(
                    driver_response_topic,
                    f"driver_{self.args.id_client}_consumer_group",  # Each Driver has an independent consumer group
                    self._handle_kafka_message,
                )

                self.logger.debug("Kafka producer initialized successfully")
                self.logger.debug(
                    f"Subscribed to unified response topic: {driver_response_topic} with driver_id filter: {self.args.id_client}"
                )
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

            # Application layer filtering: Only process messages belonging to the current Driver
            # Since using a unified response topic, need to check the driver_id field in the message
            if message_driver_id != self.args.id_client:
                # Message does not belong to current Driver, ignore (this should not happen normally due to consumer group mechanism)
                self.logger.debug(
                    f"Ignoring message for different driver: message_driver_id={message_driver_id}, "
                    f"current_driver_id={self.args.id_client}"
                )
                return

            self.logger.debug(
                f"Received Kafka message from unified topic: type={msg_type}, driver_id={message_driver_id}"
            )

            # Use message dispatcher to handle Kafka messages
            # DriverMessageDispatcher handles the following types:
            # - charge_request_response: charge request response
            # - stop_charging_response: stop charging response
            # - available_cps_response: available charging point list response
            # - charging_status_update: charging status update
            # - charging_data: real-time charging data
            # - charge_completion: charging completion notification
            self.message_dispatcher.dispatch_message(message)

        except Exception as e:
            self.logger.error(f"Error handling Kafka message: {e}", exc_info=True)

    def start(self):
        """Start Driver application"""
        self.logger.debug(f"Starting Driver module")
        self.logger.debug(
            f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )
        self.logger.info(f"Driver ID: {self.args.id_client}")

        self.running = True

        if not self._init_kafka():
            self.logger.error("Failed to initialize Kafka. Cannot start Driver.")
            print(
                "\n✗  Failed to connect to Kafka Broker. Please ensure Kafka is running and try again.\n"
            )
            self.running = False
            return

        # Request available charging point list
        self._request_available_cps()
        time.sleep(1)

        # Key change: Start CLI early so it is available in any mode
        self._init_cli()

        # Check if service file exists and store it for later use
        self.loaded_services = self._load_services_from_file()
        if self.loaded_services:
            self.logger.info(f"Loaded {len(self.loaded_services)} services from file (not auto-starting)")

        try:
            # Always start in interactive mode
            # Users can manually trigger service file processing via menu option
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
            self.logger.debug("Driver CLI initialized and started")
        except Exception as e:
            self.logger.error(f"Failed to initialize Driver CLI: {e}")
            self.driver_cli = None

    def _handle_connection_error(self, message):
        """
        处理来自Central的connection_error消息
        
        当Central停止时，会发送此消息通知Driver无法连接
        
        Args:
            message: 包含错误信息的消息字典
        """
        reason = message.get("reason", "Unknown reason")
        info = message.get("info", "Cannot connect to Central")
        
        self.logger.error(f"❌ Connection error from Central: {reason}")
        self.logger.error(f"   {info}")
        
        # 显示给用户
        self.printer.print_error("Connection Error")
        self.printer.print_key_value("Reason", reason)
        self.printer.print_key_value("Info", info)
        self.printer.print_warning("Central is shutting down. Please try again later.")
        
        # 如果有正在进行的充电会话，可能需要清理
        with self.lock:
            if self.current_charging_session:
                self.logger.warning(
                    f"Active charging session {self.current_charging_session.get('session_id')} "
                    "may be affected by Central shutdown"
                )


if __name__ == "__main__":
    import logging
    config = ConfigManager()
    debug_mode = config.get_debug_mode()
    if not debug_mode:
        logger = CustomLogger.get_logger(level=logging.INFO)
    else:
        logger = CustomLogger.get_logger(level=logging.DEBUG)
    driver = Driver(logger=logger)
    driver.start()
