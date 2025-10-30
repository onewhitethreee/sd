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
                id_client = self.config.get_client_id()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        self.central_client = None
        self.kafka_manager = None  # Kafka管理器
        self.driver_cli = None  # Driver命令行接口
        self.running = False
        self.current_charging_session = None
        self.available_charging_points = []
        self.service_queue = []
        self.charging_history = []  # 记录充电历史
        self.lock = threading.Lock()  # 线程锁，保护共享数据
        self.message_dispatcher = DriverMessageDispatcher(
            self.logger, self
        )  # 消息分发器

        # 重连机制相关
        self._reconnect_thread = None
        self._is_connected = False
        self.RECONNECT_INTERVAL = 5  # 重连间隔（秒）
        self.MAX_RECONNECT_ATTEMPTS = 0  # 0表示无限重试

    def _connect_to_central(self):
        """连接到中央系统"""
        try:
            if not self.central_client:
                self.central_client = MySocketClient(
                    logger=self.logger,
                    message_callback=self._handle_central_message,
                )

            # return self.central_client.connect(self.args.broker[0], self.args.broker[1]) # TODO 这里在换成kafka的时候需要重新吧注释删掉，目前是通过socket来连接的
            success = self.central_client.connect(
                self.config.get_ip_port_ev_cp_central()[0],
                self.config.get_ip_port_ev_cp_central()[1],
            )

            if success:
                self._is_connected = True
                self.logger.info("Successfully connected to Central")

            return success
        except Exception as e:
            self.logger.error(f"Failed to connect to Central: {e}")
            self._is_connected = False
            return False

    def _handle_central_message(self, message):
        """处理来自中央系统的消息"""
        # 使用消息分发器处理消息
        self.message_dispatcher.dispatch_message(message)


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
        """
        处理与Central的连接丢失

        当连接丢失时：
        1. 通知用户连接已断开
        2. 如果正在充电，警告用户充电状态不可知
        3. 启动自动重连机制
        """
        self._is_connected = False

        self.logger.warning("=" * 60)
        self.logger.warning("⚠️  Connection to Central has been LOST!")
        self.logger.warning("=" * 60)

        with self.lock:
            if self.current_charging_session:
                session_id = self.current_charging_session.get('session_id')
                cp_id = self.current_charging_session.get('cp_id')
                self.logger.error(
                    f"⚠️  WARNING: Active charging session detected!"
                )
                self.logger.error(f"   Session ID: {session_id}")
                self.logger.error(f"   Charging Point: {cp_id}")
                self.logger.error(
                    f"   Charging status is UNKNOWN due to connection loss."
                )
                self.logger.error(
                    f"   The charging point may have automatically stopped charging."
                )
                self.logger.error(
                    f"   Your session data will be recovered when connection is restored."
                )
                print("\n" + "!" * 60)
                print("⚠️  ATTENTION: Connection lost during active charging!")
                print("!" * 60)
                print(f"Session ID: {session_id}")
                print(f"Charging Point: {cp_id}")
                print("\nThe system will attempt to reconnect automatically.")
                print("Please wait for reconnection or restart the application.")
                print("!" * 60 + "\n")
            else:
                self.logger.info("No active charging session. Waiting for reconnection...")
                print("\n⚠️  Connection to Central lost. The system will attempt to reconnect.\n")

        # 启动自动重连线程
        self._start_reconnect_thread()

    def _start_reconnect_thread(self):
        """启动自动重连线程"""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self.logger.debug("Reconnect thread already running")
            return

        self.logger.info("Starting automatic reconnection thread...")
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True,
            name="DriverReconnectThread"
        )
        self._reconnect_thread.start()

    def _reconnect_loop(self):
        """
        自动重连循环

        持续尝试重新连接到Central，直到成功或程序退出
        """
        attempt = 0
        while self.running and not self._is_connected:
            attempt += 1

            if self.MAX_RECONNECT_ATTEMPTS > 0 and attempt > self.MAX_RECONNECT_ATTEMPTS:
                self.logger.error(
                    f"Maximum reconnection attempts ({self.MAX_RECONNECT_ATTEMPTS}) reached. Giving up."
                )
                print("\n❌ Failed to reconnect after maximum attempts. Please restart the application.\n")
                break

            self.logger.info(f"Attempting to reconnect to Central (attempt {attempt})...")
            print(f"🔄 Reconnection attempt {attempt}...")

            try:
                # 尝试重新连接
                if self._connect_to_central():
                    self.logger.info("✅ Successfully reconnected to Central!")
                    print("\n✅ Connection restored! You can now use the system normally.\n")

                    # 重连成功后的处理
                    self._handle_reconnection_success()
                    break
                else:
                    self.logger.debug(f"Reconnection attempt {attempt} failed. Retrying in {self.RECONNECT_INTERVAL} seconds...")

            except Exception as e:
                self.logger.error(f"Error during reconnection attempt: {e}")

            # 等待后再次尝试
            time.sleep(self.RECONNECT_INTERVAL)

        if not self._is_connected and self.running:
            self.logger.error("Reconnection loop ended without success")

    def _handle_reconnection_success(self):
        """
        处理重连成功后的操作

        当重连成功后：
        1. 清除之前的充电会话状态（因为可能已被Central取消）
        2. 通知用户可以重新开始操作
        """
        self.logger.info("Handling post-reconnection setup...")

        with self.lock:
            # 清除可能已过期的充电会话
            if self.current_charging_session:
                self.logger.warning(
                    f"Clearing previous charging session {self.current_charging_session.get('session_id')} "
                    f"(may have been terminated during disconnection)"
                )
                self.current_charging_session = None

            # 清空可用充电点列表（需要重新获取）
            self.available_charging_points = []

        self.logger.info("Reconnection setup complete. System ready for use.")

    def _handle_connection_error(self, message):
        """处理连接错误"""
        error = message.get("error", "Unknown error")
        self.logger.error(f"Connection error occurred: {error}")

    def _formatter_charging_points(self, charging_points):
        for i, cp in enumerate(charging_points, 1):
            print(f"【{i}】 charging point {cp['id']}")
            print(f"    ├─ Location: {cp['location']}")
            print(f"    ├─ Price/kWh: €{cp['price_per_kwh']}/kWh")
            print(f"    ├─ Status: {cp['status']}")
            print(f"    ├─ Max Charging Rate: {cp['max_charging_rate_kw']}kW")
            print()

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

        self.running = True

        # 连接到中央系统
        if not self._connect_to_central():
            self.logger.warning("Initial connection to Central failed")
            print("\n⚠️  Could not connect to Central. Starting automatic reconnection...\n")
            # 启动自动重连
            self._start_reconnect_thread()

            # 等待连接成功
            max_wait = 30  # 最多等待30秒
            wait_count = 0
            while not self._is_connected and wait_count < max_wait:
                time.sleep(1)
                wait_count += 1

            if not self._is_connected:
                self.logger.error("Failed to establish connection after waiting. Please check Central is running.")
                print("\n❌ Could not connect to Central. Please ensure Central is running and try again.\n")
                self.running = False
                return

        # 初始化Kafka
        # self._init_kafka()

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
            if self.central_client:
                self.central_client.disconnect()
            if self.kafka_manager:
                self.kafka_manager.stop()


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    driver = Driver(logger=logger)
    driver.start()

# TODO 掉线了应该有一个重试机制
