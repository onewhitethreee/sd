"""
Aplicación que usan los consumidores para usar los puntos de recarga
"""

import sys
import os
import time
import uuid
import json
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from Common.Config.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.Config.CustomLogger import CustomLogger
from Common.Config.ConfigManager import ConfigManager
from Common.Network.MySocketClient import MySocketClient
from Common.Queue.KafkaManager import KafkaManager, KafkaTopics
from Driver.DriverMessageDispatcher import DriverMessageDispatcher


class Driver:
    def __init__(self, logger=None):
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
                id_client = self.config.get_client_id()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        self.central_client = None
        self.kafka_manager = None  # Kafka管理器
        self.running = False
        self.current_charging_session = None
        self.available_charging_points = []
        self.service_queue = []
        self.charging_history = []  # 记录充电历史
        self.lock = threading.Lock()  # 线程锁，保护共享数据
        self.message_dispatcher = DriverMessageDispatcher(
            self.logger, self
        )  # 消息分发器

    def _connect_to_central(self):
        """连接到中央系统"""
        try:
            self.central_client = MySocketClient(
                logger=self.logger,
                message_callback=self._handle_central_message,
            )
            # return self.central_client.connect(self.args.broker[0], self.args.broker[1]) # TODO 这里在换成kafka的时候需要重新吧注释删掉，目前是通过socket来连接的
            return self.central_client.connect(
                self.config.get_ip_port_ev_cp_central()[0],
                self.config.get_ip_port_ev_cp_central()[1],
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to Central: {e}")
            return False

    def _handle_central_message(self, message):
        """处理来自中央系统的消息"""
        # 使用消息分发器处理消息
        self.message_dispatcher.dispatch_message(message)

    def _formatter_charging_points(self, charging_points):
        for i, cp in enumerate(charging_points, 1):
            print(f"【{i}】 charging point {cp['id']}")
            print(f"    ├─ Location: {cp['location']}")
            print(f"    ├─ Price/kWh: €{cp['price_per_kwh']}/kWh")
            print(f"    ├─ Status: {cp['status']}")
            print(f"    ├─ Max Charging Rate: {cp['max_charging_rate_kw']}kW")
            print()

    def _send_charge_request(self, cp_id):
        """发送充电请求"""
        if not self.central_client or not self.central_client.is_connected:
            self.logger.error("Not connected to Central")
            return False

        request_message = {
            "type": "charge_request",
            "message_id": str(uuid.uuid4()),
            "cp_id": cp_id,
            "driver_id": self.args.id_client,
        }

        self.logger.info(f"🚗 Sending charging request for CP: {cp_id}")
        return self.central_client.send(request_message)

    def _send_stop_charging_request(self):
        """发送停止充电请求"""
        with self.lock:
            if not self.current_charging_session:
                self.logger.warning("No active charging session to stop")
                return False

            session_id = self.current_charging_session["session_id"]
            cp_id = self.current_charging_session["cp_id"]

        if not self.central_client or not self.central_client.is_connected:
            self.logger.error("Not connected to Central")
            return False

        request_message = {
            "type": "stop_charging_request",
            "message_id": str(uuid.uuid4()),
            "session_id": session_id,
            "cp_id": cp_id,
            "driver_id": self.args.id_client,
        }

        self.logger.info(f"🛑 Sending stop charging request for session: {session_id}")
        return self.central_client.send(request_message)

    def _request_available_cps(self):
        """请求可用充电点列表"""
        if not self.central_client or not self.central_client.is_connected:
            self.logger.error("Not connected to Central")
            return False

        request_message = {
            "type": "available_cps_request",
            "message_id": str(uuid.uuid4()),
            "driver_id": self.args.id_client,
            "timestamp": int(time.time()),
        }

        return self.central_client.send(request_message)

    def _load_services_from_file(self, filename="test_services.txts"):
        """从文件加载服务列表"""
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

    def _handle_connection_lost(self):
        """处理连接丢失"""
        self.logger.warning("Connection to Central has been lost")
        with self.lock:
            if self.current_charging_session:
                self.logger.warning(
                    f"Active charging session {self.current_charging_session.get('session_id')} may be affected"
                )

    def _handle_connection_error(self, message):
        """处理连接错误"""
        error = message.get("error", "Unknown error")
        self.logger.error(f"Connection error occurred: {error}")

    def _show_charging_history(self):
        """显示充电历史"""
        if not self.charging_history:
            self.logger.info("No charging history available")
            return

        self.logger.info("\n" + "=" * 60)
        self.logger.info("Charging History")
        self.logger.info("=" * 60)
        for i, record in enumerate(self.charging_history, 1):
            self.logger.info(f"\n【{i}】 Session: {record['session_id']}")
            self.logger.info(f"    CP ID: {record['cp_id']}")
            self.logger.info(f"    Completion Time: {record['completion_time']}")
            self.logger.info(f"    Energy: {record['energy_consumed_kwh']:.3f}kWh")
            self.logger.info(f"    Cost: €{record['total_cost']:.2f}")
        self.logger.info("=" * 60 + "\n")

    def _process_next_service(self):
        """处理下一个服务"""
        if self.service_queue:
            cp_id = self.service_queue.pop(0)
            self.logger.info(f"Processing next service: {cp_id}")
            self._send_charge_request(cp_id)
        else:
            self.logger.info("No more services to process")
            self._show_charging_history()

    def _interactive_mode(self):
        """交互模式"""
        self.logger.info("Entering interactive mode. Available commands:")
        self.logger.info("  - 'list': Show available charging points")
        self.logger.info("  - 'charge <cp_id>': Request charging at specific CP")
        self.logger.info("  - 'stop': Stop current charging session")
        self.logger.info("  - 'status': Show current charging status")
        self.logger.info("  - 'history': Show charging history")
        self.logger.info("  - 'help': Show this help message")
        self.logger.info("  - 'quit': Exit application")

        while self.running:
            try:
                command = input("\nDriver> ").strip().lower()

                if command == "quit":
                    self.running = False
                    break
                elif command == "list":
                    self._request_available_cps()
                elif command.startswith("charge "):
                    cp_id = command.split(" ", 1)[1]
                    self._send_charge_request(cp_id)
                elif command == "stop":
                    self._send_stop_charging_request()
                elif command == "status":
                    with self.lock:
                        if self.current_charging_session:
                            session = self.current_charging_session
                            self.logger.info(
                                f"Current session: {session['session_id']}"
                            )
                            self.logger.info(f"  CP ID: {session['cp_id']}")
                            self.logger.info(
                                f"  Energy: {session['energy_consumed_kwh']:.3f}kWh"
                            )
                            self.logger.info(f"  Cost: €{session['total_cost']:.2f}")
                            self.logger.info(
                                f"  Rate: {session['charging_rate']:.2f}kW"
                            )
                        else:
                            self.logger.info("No active charging session")
                elif command == "history":
                    self._show_charging_history()
                elif command == "help":
                    self.logger.info("Available commands:")
                    self.logger.info("  - 'list': Show available charging points")
                    self.logger.info(
                        "  - 'charge <cp_id>': Request charging at specific CP"
                    )
                    self.logger.info("  - 'stop': Stop current charging session")
                    self.logger.info("  - 'status': Show current charging status")
                    self.logger.info("  - 'history': Show charging history")
                    self.logger.info("  - 'help': Show this help message")
                    self.logger.info("  - 'quit': Exit application")
                else:
                    self.logger.info(
                        "Unknown command. Type 'help' for available commands."
                    )

            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                self.logger.error(f"Error in interactive mode: {e}")

    def _auto_mode(self, services):
        """自动模式"""
        self.logger.info(f"Entering auto mode with {len(services)} services")
        self.service_queue = services.copy()

        # 处理第一个服务
        if self.service_queue:
            self._process_next_service()

        # 等待所有服务完成
        while self.running and (self.service_queue or self.current_charging_session):
            time.sleep(1)

    def _init_kafka(self):
        """初始化Kafka连接"""
        try:
            broker_address = f"{self.args.broker[0]}:{self.args.broker[1]}"
            self.kafka_manager = KafkaManager(broker_address, self.logger)

            if self.kafka_manager.init_producer():
                self.kafka_manager.start()

                # 初始化消费者订阅相关主题
                self.kafka_manager.init_consumer(
                    KafkaTopics.DRIVER_CHARGING_STATUS,
                    f"driver_{self.args.id_client}",
                    self._handle_kafka_message,
                )
                self.kafka_manager.init_consumer(
                    KafkaTopics.DRIVER_CHARGING_COMPLETE,
                    f"driver_{self.args.id_client}",
                    self._handle_kafka_message,
                )

                self.logger.info("Kafka initialized successfully")
                return True
            else:
                self.logger.warning("Failed to initialize Kafka producer")
                return False
        except Exception as e:
            self.logger.error(f"Error initializing Kafka: {e}")
            return False

    def _handle_kafka_message(self, message):
        """处理来自Kafka的消息"""
        try:
            self.logger.debug(f"Received Kafka message: {message}")
            # 这里可以添加具体的消息处理逻辑
        except Exception as e:
            self.logger.error(f"Error handling Kafka message: {e}")

    def start(self):
        """启动Driver应用"""
        self.logger.info(f"Starting Driver module")
        self.logger.info(
            f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )
        self.logger.info(f"Client ID: {self.args.id_client}")

        # 连接到中央系统
        if not self._connect_to_central():
            self.logger.error("Failed to connect to Central")
            return

        # 初始化Kafka
        # self._init_kafka()

        self.running = True

        # 请求可用充电点列表
        self._request_available_cps()
        time.sleep(2)

        # 检查是否有服务文件
        services = self._load_services_from_file()

        try:
            if services:
                # 自动模式
                self._auto_mode(services)
            else:
                # 交互模式
                self._interactive_mode()

        except KeyboardInterrupt:
            self.logger.info("Shutting down Driver")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
        finally:
            self.running = False
            if self.central_client:
                self.central_client.disconnect()
            if self.kafka_manager:
                self.kafka_manager.stop()


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    driver = Driver(logger=logger)
    driver.start()

# TODO 掉线了应该有一个重试机制
