"""
Módulo que recibe la información de los sensores y se conecta al sistema monitor
"""

import sys
import os
import time
import threading
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Config.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.Config.ConfigManager import ConfigManager
from Common.Config.CustomLogger import CustomLogger
from Common.Network.MySocketServer import MySocketServer
from Common.Config.Status import Status
from Common.Queue.KafkaManager import KafkaManager, KafkaTopics
from Charging_point.Engine.EngineMessageDispatcher import EngineMessageDispatcher
from Charging_point.Engine.EngineCLI import EngineCLI


class EV_CP_E:
    def __init__(self, logger=None):
        self.logger = logger
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()

        if not self.debug_mode:
            self.tools = AppArgumentParser(
                "EV_CP_E", "Módulo de gestión de sensores y comunicación con la monitor"
            )
            self.tools.add_argument(
                "broker",
                type=ip_port_type,
                help="IP y puerto del Broker/Bootstrap-server (formato IP:PORT)",
            )
            self.args = self.tools.parse_args()

            # 非 debug 模式：从环境变量读取监听端口，如果没有则使用端口 0（自动分配）
            listen_adress = os.getenv("IP_PORT_EV_CP_E")
            listen_host = listen_adress.split(":")[0] if listen_adress else "localhost"
            listen_port = listen_adress.split(":")[1] if listen_adress else None

            if listen_port:
                self.engine_listen_address = (listen_host, int(listen_port))
                self.logger.info(f"Using ENGINE_LISTEN_PORT from environment: {listen_port}")
            else:
                # 端口 0 表示让操作系统自动分配可用端口
                self.engine_listen_address = (listen_host, 0)
                self.logger.info("No ENGINE_LISTEN_PORT specified, will use automatic port assignment")
        else:

            class Args:
                broker = self.config.get_broker()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

            # debug 模式：从配置文件读取Engine监听地址
            self.engine_listen_address = self.config.get_ip_port_ev_cp_e()

        self.running = False
        self.monitor_server: MySocketServer = None
        self.kafka_manager: KafkaManager = None  # Kafka管理器

        self.current_session = None

        self.cp_id = None
        self._id_initialized = False

        # Flag para simular fallo manual (usado por CLI)
        # Cuando está en True, get_current_status() siempre retorna FAULTY
        self._manual_faulty_mode = False

        self.message_dispatcher = EngineMessageDispatcher(self.logger, self)
        self.engine_cli = None  # CLI para simular acciones del usuario (enchufar/desenchufar vehículo)

    @property
    def is_charging(self):
        """返回当前是否正在充电（只读属性）"""
        return self.current_session is not None

    def set_cp_id(self, cp_id: str):
        """
        设置充电桩ID（由Monitor提供）

        Args:
            cp_id: 充电桩ID

        Returns:
            bool: 设置是否成功
        """
        if self._id_initialized:
            self.logger.warning(f"CP_ID already initialized as {self.cp_id}, ignoring new ID: {cp_id}")
            return False

        self.cp_id = cp_id
        self._id_initialized = True
        self.logger.info(f"✅ CP_ID initialized: {self.cp_id}")
        return True

    def get_current_status(self):
        """返回Engine当前状态"""
        # Si está en modo de fallo manual, siempre retorna FAULTY
        if self._manual_faulty_mode:
            return Status.FAULTY.value
        elif self.is_charging:
            return Status.CHARGING.value
        elif not self.running:
            return Status.FAULTY.value
        else:
            return Status.ACTIVE.value

    def _process_monitor_message(self, client_id, message):
        """处理来自Monitor的消息"""
        self.logger.debug(
            f"Received message from Monitor {client_id}: {message.get('type')}"
        )
        return self.message_dispatcher.dispatch_message(message)

    def _handle_monitor_disconnect(self, client_id):
        """处理Monitor断开连接"""
        self.logger.warning(f"Monitor {client_id} disconnected")
        # 进入安全模式：停止当前充电会话
        if self.is_charging:
            self.logger.warning(
                "Monitor disconnected during charging - stopping charging for safety"
            )
            self._stop_charging_session()

        # 不要立即进入 FAULTY 状态，Monitor 可能会重连。
        #  TODO 如果长时间没有 monitor 连接，可以考虑定时检查并切换状态。

    def _start_monitor_server(self):
        """启动服务器等待Monitor连接"""

        try:
            self.monitor_server = MySocketServer(
                host=self.engine_listen_address[0],
                port=self.engine_listen_address[1],
                logger=self.logger,
                message_callback=self._process_monitor_message,
                disconnect_callback=self._handle_monitor_disconnect,
            )

            self.monitor_server.start()

            # 获取实际绑定的端口（当使用端口 0 时会自动分配）
            actual_port = self.monitor_server.get_actual_port()
            actual_host = self.engine_listen_address[0]

            # 更新实际的监听地址
            self.engine_listen_address = (actual_host, actual_port)

            self.logger.info(
                f"Monitor server started on {actual_host}:{actual_port}"
            )

            # 如果端口是自动分配的，用醒目的方式显示
            if self.monitor_server.port == 0:
                print("\n" + "="*60)
                print(f"  ENGINE LISTENING ON: {actual_host}:{actual_port}")
                print(f"  Use this address to start Monitor:")
                print(f"  python EV_CP_M.py {actual_host}:{actual_port} <central_address:central port> <cp_id>")
                print("="*60 + "\n")

            return True

        except Exception as e:
            self.logger.error(f"Error starting monitor server: {e}")
            return False

    def _init_connections(self):
        """初始化连接"""
        try:
            if not self._start_monitor_server():
                raise Exception("Failed to start monitor server")

            # 初始化Kafka客户端
            self._init_kafka()  

            self.running = True
            return True

        except Exception as e:
            self.logger.error(f"Error initializing connections: {e}")
            return False

    def _init_kafka(self):
        """初始化Kafka连接"""

        broker_address = f"{self.args.broker[0]}:{self.args.broker[1]}"

        try:
            self.kafka_manager = KafkaManager(broker_address, self.logger)

            if self.kafka_manager.init_producer():
                self.kafka_manager.start()

                # 创建所需的 topics
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

                self.logger.info("Kafka producer initialized successfully")
                return True
            else:
                self.logger.warning("Failed to initialize Kafka producer")
                return False
        except Exception as e:
            self.logger.error(f"Error initializing Kafka: {e}")
            self.kafka_manager = None
            return False

    def _shutdown_system(self):
        """关闭系统"""
        self.logger.info("Starting system shutdown...")
        self.running = False

        if self.is_charging:
            self._stop_charging_session()
            # 不需要设置 self.is_charging = False，因为 _stop_charging_session() 会设置 current_session = None

        if self.engine_cli:
            self.engine_cli.stop()

        if self.monitor_server:
            self.monitor_server.stop()

        if self.kafka_manager:
            self.kafka_manager.stop()

        self.logger.info("System shutdown complete")

    def _start_charging_session(
        self,
        driver_id: str,
        session_id: str,
        price_per_kwh: float = 0.0,
    ):
        """
        启动充电会话。

        Args:
            driver_id: 司机/电动车ID
            session_id: 充电会话ID（由Central通过Monitor提供）
            price_per_kwh: 每度电价格（从Central/ChargingPoint获取）
        """
        self.logger.info(
            f"Starting charging session '{session_id}' for Driver: {driver_id}, price: €{price_per_kwh}/kWh"
        )
        if self.is_charging:
            self.logger.warning("Already charging, cannot start new session.")
            return False

        self.current_session = {
            "session_id": session_id,
            "driver_id": driver_id,
            "start_time": time.time(),
            "energy_consumed_kwh": 0.0,  # 初始能量
            "total_cost": 0.0,  # 初始费用
            "price_per_kwh": price_per_kwh,  # 每度电价格
        }
        # 启动充电线程
        charging_thread = threading.Thread(
            target=self._charging_process,
            args=(session_id,),
            daemon=True,  # 传递 session_id 以确保操作的是正确会话
        )
        charging_thread.start()
        self.logger.info(
            f"Charging session {self.current_session['session_id']} "
        )
        return True

    def _stop_charging_session(self):
        """停止充电会话。 因为一个ChargingPoint只能有一个充电会话。"""
        self.logger.info(f"Stopping charging for session {self.current_session['session_id']}... ")
        if not self.is_charging:
            self.logger.warning("No active charging session to stop.")
            return False

        session_id = self.current_session["session_id"]
        driver_id = self.current_session["driver_id"]
        self.logger.info(f"Stopping charging session '{session_id}' for Driver: {driver_id}")
        # 设置 current_session 为 None，这将导致 _charging_process 停止
        # 这是通过 is_charging property 来实现终止的简洁方式
        # --- 重点：设置 current_session 为 None 即可退出充电状态 ---

        # 确保在清除 current_session 之前保存最终数据
        final_session_data = self.current_session.copy()
        final_session_data["end_time"] = time.time()
        final_session_data["duration"] = (
            final_session_data["end_time"] - final_session_data["start_time"]
        )

        self.current_session = None  # 停止充电循环的信号
        self.logger.info(f"Charging session {session_id} completed:")
        self.logger.info(f"  Duration: {final_session_data['duration']:.1f} seconds")
        self.logger.info(
            f"  Energy consumed: {final_session_data['energy_consumed_kwh']:.2f} kWh"
        )
        self.logger.info(f"  Total cost: €{final_session_data['total_cost']:.2f}")
        self._send_charging_completion(final_session_data)  # 发送完成通知
        return True

    def _charging_process(self, session_id_to_track: str):
        """充电过程模拟（30秒后自动停止）"""
        self.logger.info(f"Charging process started for session {session_id_to_track}.")

        # 记录充电开始时间用于30秒自动停止
        charging_start_time = time.time()
        MAX_CHARGING_DURATION = 30  # 30秒后自动停止

        # 确保线程仅针对其启动的会话运行
        while (
            self.is_charging
            and self.running
            and self.current_session
            and self.current_session["session_id"] == session_id_to_track
        ):
            try:
                time.sleep(1)
                if not self.is_charging or not self.current_session:
                    break

                # 检查是否已经充电30秒
                elapsed_time = time.time() - charging_start_time
                if elapsed_time >= MAX_CHARGING_DURATION:
                    self.logger.info(
                        f"Session {session_id_to_track} reached {MAX_CHARGING_DURATION} seconds - auto-stopping (charging complete)"
                    )
                    self._stop_charging_session()
                    break

                self.current_session["energy_consumed_kwh"] += 0.01
                self.current_session["total_cost"] = (
                    self.current_session["energy_consumed_kwh"]
                    * self.current_session["price_per_kwh"]
                )
                self._send_charging_data()  # 发送充电数据到Monitor和Kafka
                self.logger.debug(
                    f"Session {session_id_to_track} progress: {self.current_session['energy_consumed_kwh']:.3f} kWh, €{self.current_session['total_cost']:.2f}, elapsed: {elapsed_time:.1f}s/{MAX_CHARGING_DURATION}s"
                )
            except Exception as e:
                self.logger.error(
                    f"Error in charging process for session {session_id_to_track}: {e}"
                )
                break
        self.logger.info(f"Charging process ended for session {session_id_to_track}.")

    def _send_charging_data(self):
        """发送充电数据到Monitor和Kafka（改进版）"""
        if not self.current_session:  # 如果没有活跃会话，直接返回
            return

        charging_data_message = {
            "type": "charging_data",
            "message_id": str(uuid.uuid4()),  # 用于幂等性
            "cp_id": self.cp_id,  # ✅ 使用从Monitor接收的cp_id
            "session_id": self.current_session["session_id"],
            "energy_consumed_kwh": round(
                self.current_session["energy_consumed_kwh"], 3
            ),
            "total_cost": round(self.current_session["total_cost"], 2),
            "timestamp": int(time.time()),
        }

        # 发送到 Monitor（Socket，保持向后兼容）
        if self.monitor_server and self.monitor_server.has_active_clients():
            self.monitor_server.send_broadcast_message(charging_data_message)
            self.logger.debug(
                f"Charging data sent to Monitor: {charging_data_message['session_id']}"
            )
        else:
            self.logger.debug("No active monitor clients to send charging data.")

        # ✅ 发送到 Kafka（改进版）
        if self.kafka_manager and self.kafka_manager.is_connected():
            success = self.kafka_manager.produce_message(
                KafkaTopics.CHARGING_SESSION_DATA, charging_data_message
            )
            if success:
                self.logger.debug(
                    f"Charging data sent to Kafka: {charging_data_message['session_id']}"
                )
            else:
                self.logger.error("Failed to send charging data to Kafka")
        else:
            self.logger.debug(
                "Kafka not available, charging data only sent to Monitor"
            )

    def _send_charging_completion(self, final_session_data: dict):
        """发送充电完成通知到Monitor和Kafka（改进版）"""
        if not final_session_data:  # 如果没有数据，直接返回
            return

        completion_message = {
            "type": "charge_completion",
            "message_id": str(uuid.uuid4()),  # 用于幂等性
            "cp_id": self.cp_id,  # ✅ 使用从Monitor接收的cp_id
            "session_id": final_session_data["session_id"],
            "energy_consumed_kwh": round(final_session_data["energy_consumed_kwh"], 3),
            "total_cost": round(final_session_data["total_cost"], 2),
            "timestamp": int(time.time()),  # 添加时间戳
        }

        # 1. 发送到 Monitor（Socket，向后兼容）
        if self.monitor_server and self.monitor_server.has_active_clients():
            self.monitor_server.send_broadcast_message(completion_message)
            self.logger.info(
                f"Charging completion sent to Monitor: {completion_message['session_id']}"
            )
        else:
            self.logger.debug(
                "No active monitor clients to send charging completion."
            )

        # 2. 发送到 Kafka（改进版）
        if self.kafka_manager and self.kafka_manager.is_connected():
            success = self.kafka_manager.produce_message(
                KafkaTopics.CHARGING_SESSION_COMPLETE, completion_message
            )
            if success:
                self.logger.info(
                    f"Charging completion sent to Kafka: {completion_message['session_id']}"
                )
            else:
                self.logger.error("Failed to send charging completion to Kafka")
        else:
            self.logger.debug(
                "Kafka not available, charging completion only sent to Monitor"
            )

    def _init_cli(self):
        """初始化Engine CLI（según PDF página 7 y 11）"""
        try:
            self.engine_cli = EngineCLI(self, self.logger)
            self.engine_cli.start()
            self.logger.info("Engine CLI initialized successfully")
            self.logger.info("Press ENTER to show interactive menu for manual operations")
        except Exception as e:
            self.logger.error(f"Failed to initialize Engine CLI: {e}")
            self.engine_cli = None

    def initialize_system(self):
        """初始化系统"""
        self.logger.info("Initializing EV_CP_E module")
        return self._init_connections()

    def start(self):
        self.logger.info(
            f"Will listen for Monitor on {self.engine_listen_address[0]}:{self.engine_listen_address[1]}"
        )
        self.logger.info(
            f"Will connect to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )

        if not self.initialize_system():
            self.logger.error("Failed to initialize system")
            sys.exit(1)

        # Iniciar CLI para simular acciones del usuario (según PDF página 7 y 11)
        self._init_cli()

        try:

            self.running = True
            while self.running:
                time.sleep(0.1)  # 保持运行

        except KeyboardInterrupt:
            self.logger.info("Shutting down EV_CP_E")
            self._shutdown_system()
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self._shutdown_system()


if __name__ == "__main__":
    import logging
    logger = CustomLogger.get_logger(level=logging.DEBUG)
    ev_cp_e = EV_CP_E(logger=logger)
    ev_cp_e.start()
