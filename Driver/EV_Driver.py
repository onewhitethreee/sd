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
from Common.Queue.KafkaManager import KafkaManager, KafkaTopics
from Driver.DriverMessageDispatcher import DriverMessageDispatcher
from Driver.DriverCLI import DriverCLI


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
                import random
                id_client = f"driver_{random.randint(0,99999)}"

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        self.kafka_manager = None  # Kafka管理器
        self.driver_cli = None  # Driver命令行接口
        self.running = False

        # ========== 状态管理（遵循 CQRS 原则）==========
        # 实时状态：从 Kafka 订阅实时更新
        self.current_charging_session = None  # 当前充电会话的实时状态

        # 缓存数据：短期缓存，用于减少查询
        self.available_charging_points = []  # 可用充电桩列表（短期缓存）
        self.available_cps_cache_time = None  # 缓存时间戳

        # 历史数据：不在内存中存储，通过查询 API 按需获取
        # self.charging_history = []  # ❌ 已移除：改用远程查询

        # 自动模式队列（仅用于自动模式的本地调度）
        self.service_queue = []

        self.lock = threading.Lock()  # 线程锁，保护共享数据
        self.message_dispatcher = DriverMessageDispatcher(
            self.logger, self
        )  # 消息分发器



    def _send_charge_request(self, cp_id):
        """发送充电请求（纯Kafka模式）"""
        request_message = {
            "type": "charge_request",
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
        """发送停止充电请求（纯Kafka模式）"""
        with self.lock:
            if not self.current_charging_session:
                self.logger.warning("No active charging session to stop")
                return False

            session_id = self.current_charging_session["session_id"]
            cp_id = self.current_charging_session["cp_id"]

        request_message = {
            "type": "stop_charging_request",
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
        """请求可用充电点列表（纯Kafka模式）"""
        request_message = {
            "type": "available_cps_request",
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

    def _request_charging_history(self, limit=None):
        """
        请求充电历史记录（查询模式 via Kafka）

        这是一个查询请求，不是事件订阅。
        Driver 发送查询请求到 Kafka，Central 从数据库查询后返回结果。

        Args:
            limit: 可选，限制返回的历史记录数量

        Returns:
            bool: 请求是否成功发送
        """
        request_message = {
            "type": "charging_history_request",
            "message_id": str(uuid.uuid4()),
            "driver_id": self.args.id_client,
            "timestamp": int(time.time()),
        }

        if limit:
            request_message["limit"] = limit

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


    def _formatter_charging_points(self, charging_points):
        for i, cp in enumerate(charging_points, 1):
            print(f"【{i}】 charging point {cp['id']}")
            print(f"    ├─ Location: {cp['location']}")
            print(f"    ├─ Price/kWh: €{cp['price_per_kwh']}/kWh")
            print(f"    ├─ Status: {cp['status']}")
            print(f"    ├─ Max Charging Rate: {cp['max_charging_rate_kw']}kW")
            print()

    def _show_charging_history(self, history_data=None):
        """
        显示充电历史（从远程查询获取）

        Args:
            history_data: 可选，充电历史数据列表。如果不提供，将发起查询请求
        """
        if history_data is None:
            self.logger.info("Requesting charging history from Central...")
            # 发起查询请求，响应会异步到达并由 DriverMessageDispatcher 处理
            self._request_charging_history()
            return

        if not history_data:
            self.logger.info("No charging history available")
            return

        self.logger.info("\n" + "=" * 60)
        self.logger.info("Charging History")
        self.logger.info("=" * 60)
        for i, record in enumerate(history_data, 1):
            self.logger.info(f"\n【{i}】 Session: {record.get('session_id', 'N/A')}")
            self.logger.info(f"    CP ID: {record.get('cp_id', 'N/A')}")
            self.logger.info(f"    Start Time: {record.get('start_time', 'N/A')}")
            self.logger.info(f"    End Time: {record.get('end_time', 'N/A')}")
            self.logger.info(f"    Energy: {record.get('energy_consumed_kwh', 0):.3f}kWh")
            self.logger.info(f"    Cost: €{record.get('total_cost', 0):.2f}")
        self.logger.info("=" * 60 + "\n")

    def _process_next_service(self):
        """处理下一个服务"""
        if self.service_queue:
            cp_id = self.service_queue.pop(0)
            self.logger.info(f"Processing next service: {cp_id}")
            self._send_charge_request(cp_id)
        else:
            self.logger.info("No more services to process")
            # 查询并显示充电历史（异步，响应会通过 Kafka 返回）
            self._request_charging_history()

    def _interactive_mode(self):
        """交互模式 - 使用DriverCLI"""
        self.logger.info("Entering interactive mode...")

        # 初始化并启动DriverCLI
        self.driver_cli = DriverCLI(self)
        self.driver_cli.start()

        # 等待CLI运行
        try:
            while self.running and self.driver_cli.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        # 不在这里停止CLI，让外层的finally统一处理清理工作

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
        """初始化Kafka连接（改进版）"""
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
                    num_partitions=1,
                    replication_factor=1
                )
                self.kafka_manager.create_topic_if_not_exists(
                    KafkaTopics.DRIVER_CPS_REQUESTS,
                    num_partitions=1,
                    replication_factor=1
                )
                # 创建该Driver的专属响应主题（每个Driver独立主题，实现消息隔离）
                driver_response_topic = KafkaTopics.get_driver_response_topic(self.args.id_client)
                self.kafka_manager.create_topic_if_not_exists(
                    driver_response_topic,
                    num_partitions=1,  # 每个Driver只需要1个分区
                    replication_factor=1
                )

                # 订阅该Driver的专属响应主题
                # 重要：使用独立主题后，不再需要应用层过滤，Kafka层已经实现了消息隔离
                self.kafka_manager.init_consumer(
                    driver_response_topic,
                    f"driver_{self.args.id_client}_consumer_group",  # consumer group
                    self._handle_kafka_message,
                )

                self.logger.info("Kafka producer initialized successfully")
                self.logger.info(f"Subscribed to personal response topic: {driver_response_topic}")
                return True
            else:
                self.logger.error("Failed to initialize Kafka producer")
                return False

        except Exception as e:
            self.logger.error(f"Kafka初始化失败: {e}")
            return False

    def _handle_kafka_message(self, message):
        """处理来自Kafka的消息"""
        try:
            msg_type = message.get("type")

            # 由于每个Driver使用独立的响应主题，所以收到的所有消息都是属于当前Driver的
            # 不再需要应用层过滤，Kafka主题隔离已经保证了消息的正确路由
            self.logger.debug(f"Received Kafka message from personal topic: type={msg_type}")

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

        # 初始化Kafka（唯一的通信方式）
        if not self._init_kafka():
            self.logger.error("Failed to initialize Kafka. Cannot start Driver.")
            print("\n❌ Failed to connect to Kafka Broker. Please ensure Kafka is running and try again.\n")
            self.running = False
            return

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
            if self.driver_cli:
                self.driver_cli.stop()
            if self.kafka_manager:
                self.kafka_manager.stop()


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    driver = Driver(logger=logger)
    driver.start()
