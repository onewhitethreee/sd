"""
Módulo que recibe la información de los sensores y se conecta al sistema monitor
"""

import sys
import os
import time
import threading
import uuid
import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Config.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.Config.ConfigManager import ConfigManager
from Common.Config.CustomLogger import CustomLogger
from Common.Network.MySocketServer import MySocketServer
from Common.Config.Status import Status
from Common.Queue.KafkaManager import KafkaManager, KafkaTopics
from Charging_point.Engine.EngineMessageDispatcher import EngineMessageDispatcher


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
            # TODO 这里需要检查一下当用命令行来创建多个 ChargingPoint 时，id_cp 是如何处理的
        else:

            class Args:
                broker = self.config.get_broker()
                id_cp = self.config.get_id_cp()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        # 从配置获取Engine监听地址
        self.engine_listen_address = self.config.get_ip_port_ev_cp_e()

        self.running = False
        self.is_charging = False
        self.monitor_server: MySocketServer = None
        self.kafka_manager: KafkaManager = None  # Kafka管理器

        self.current_session = None

        # 初始化消息分发器
        self.message_dispatcher = EngineMessageDispatcher(self.logger, self)

    @property
    def is_charging(self):
        return self.current_session is not None

    @is_charging.setter
    def is_charging(self, value):
        self._is_charging = value

    def get_current_status(self):
        """返回Engine当前状态"""
        if self.is_charging:
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
            self.logger.info(
                f"Monitor server started on {self.engine_listen_address[0]}:{self.engine_listen_address[1]}"
            )
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
            # self._init_kafka()

            self.running = True
            return True

        except Exception as e:
            self.logger.error(f"Error initializing connections: {e}")
            return False

    def _init_kafka(self):
        """初始化Kafka连接"""

        if self.debug_mode:
            broker_address = f"{self.args.broker[0]}:{self.args.broker[1]}"
        else:
            broker_address = f"{self.args.broker[0]}:{self.args.broker[1]}"

        try:
            self.kafka_manager = KafkaManager(broker_address, self.logger)

            if self.kafka_manager.init_producer():
                self.kafka_manager.start()
                self.logger.info("Kafka producer initialized successfully")
            else:
                self.logger.warning("Failed to initialize Kafka producer")
        except Exception as e:
            self.logger.error(f"Error initializing Kafka: {e}")
            self.kafka_manager = None

    def _shutdown_system(self):
        """关闭系统"""
        self.logger.info("Starting system shutdown...")
        self.running = False

        if self.is_charging:
            self._stop_charging_session()
            self.is_charging = False

        if self.monitor_server:
            self.monitor_server.stop()  

        if self.kafka_manager:
            self.kafka_manager.stop()

        self.logger.info("System shutdown complete")

    def _start_charging_session(
        self,
        ev_id: str,
        session_id: str,
        price_per_kwh: float = 0.0,
        max_charging_rate_kw: float = 11.0,
    ):
        """
        启动充电会话。

        Args:
            ev_id: 电动车ID
            session_id: 充电会话ID（由Central通过Monitor提供）
            price_per_kwh: 每度电价格（从Central/ChargingPoint获取）
            max_charging_rate_kw: 最大充电速率（从Central/ChargingPoint获取）
        """
        self.logger.info(
            f"Starting charging session '{session_id}' for EV: {ev_id}, price: €{price_per_kwh}/kWh, max rate: {max_charging_rate_kw}kW"
        )
        if self.is_charging:
            self.logger.warning("Already charging, cannot start new session.")
            return False

        # 充电速率：在最大充电速率范围内随机生成（模拟不同的充电功率）
        # 实际充电速率不会超过充电桩的最大能力
        min_rate = min(5.0, max_charging_rate_kw * 0.5)  # 最小速率为最大速率的50%或5kW
        charging_rate_kw = random.uniform(min_rate, max_charging_rate_kw)

        self.current_session = {
            "session_id": session_id,
            "ev_id": ev_id,
            "start_time": time.time(),
            "energy_consumed_kwh": 0.0,  # 初始能量
            "total_cost": 0.0,  # 初始费用
            "charging_rate_kw": charging_rate_kw,  # 充电速率（千瓦）
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
            f"Charging session {self.current_session['session_id']} started with rate {self.current_session['charging_rate_kw']:.1f} kW."
        )
        return True

    def _stop_charging_session(self):
        """停止充电会话。不再需要 ev_id 参数。 因为一个ChargingPoint只能有一个充电会话。"""
        self.logger.info(f"Stopping charging for session {self.current_session['session_id']}... ")
        if not self.is_charging:
            self.logger.warning("No active charging session to stop.")
            return False

        session_id = self.current_session["session_id"]
        ev_id = self.current_session["ev_id"]
        self.logger.info(f"Stopping charging session '{session_id}' for EV: {ev_id}")
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
        """充电过程模拟"""
        self.logger.info(f"Charging process started for session {session_id_to_track}.")
        # 确保线程仅针对其启动的会话运行
        while (
            self.is_charging
            and self.running
            and self.current_session
            and self.current_session["session_id"] == session_id_to_track
        ):
            try:
                time.sleep(1)  # 每秒更新
                # 如果过程中停止充电，current_session 会变为 None，循环就会退出
                if not self.is_charging or not self.current_session:
                    break
                # --- 重点：单位计算修正 ---
                # charging_rate_kw 是千瓦 (kW)，每秒消耗的能量是 kW / 3600 (kWh)
                energy_this_second_kwh = (
                    self.current_session["charging_rate_kw"] / 3600.0
                )  # kWh/秒

                self.current_session["energy_consumed_kwh"] += energy_this_second_kwh
                self.current_session["total_cost"] = (
                    self.current_session["energy_consumed_kwh"]
                    * self.current_session["price_per_kwh"]
                )
                self._send_charging_data()  # 发送充电数据到Monitor和Kafka
                self.logger.debug(
                    f"Session {session_id_to_track} progress: {self.current_session['energy_consumed_kwh']:.3f} kWh, €{self.current_session['total_cost']:.2f}"
                )
            except Exception as e:
                self.logger.error(
                    f"Error in charging process for session {session_id_to_track}: {e}"
                )
                break
        self.logger.info(f"Charging process ended for session {session_id_to_track}.")

    def _send_charging_data(self):
        """发送充电数据到Monitor和Kafka"""
        if not self.current_session:  # 如果没有活跃会话，直接返回
            return

        charging_data_message = {
            "type": "charging_data",
            "message_id": str(uuid.uuid4()),
            "cp_id": self.args.id_cp,
            "session_id": self.current_session["session_id"],
            "energy_consumed_kwh": round(
                self.current_session["energy_consumed_kwh"], 3
            ),
            "total_cost": round(self.current_session["total_cost"], 2),
            "charging_rate": round(
                self.current_session["charging_rate_kw"], 1
            ), 
        }
        # 发送到 Monitor
        if self.monitor_server and self.monitor_server.has_active_clients():
            self.monitor_server.send_broadcast_message(charging_data_message)
            self.logger.debug(
                f"Charging data sent to Monitor: {charging_data_message['session_id']}"
            )
        else:
            self.logger.debug("No active monitor clients to send charging data.")
        # 发送到 Kafka
        if self.kafka_manager:
            self.kafka_manager.produce_message(
                KafkaTopics.CHARGING_SESSION_DATA, charging_data_message
            )
            self.logger.debug(
                f"Charging data sent to Kafka: {charging_data_message['session_id']}"
            )
        else:
            self.logger.debug(
                "Kafka manager not initialized, skipped sending charging data."
            )

    def _send_charging_completion(self, final_session_data: dict):
        """发送充电完成通知到Monitor和Kafka"""
        if not final_session_data:  # 如果没有数据，直接返回
            return
        completion_message = {
            "type": "charge_completion",
            "message_id": str(uuid.uuid4()),
            "cp_id": self.args.id_cp,
            "session_id": final_session_data["session_id"],
            "energy_consumed_kwh": round(final_session_data["energy_consumed_kwh"], 3),
            "total_cost": round(final_session_data["total_cost"], 2),
        }
        if self.monitor_server and self.monitor_server.has_active_clients():
            self.monitor_server.send_broadcast_message(completion_message)
            self.logger.info(
                f"Charging completion sent to Monitor: {completion_message['session_id']}"
            )
        else:
            self.logger.warning(
                "No active monitor clients to send charging completion."
            )
        # 发送到 Kafka
        if self.kafka_manager:
            self.kafka_manager.produce_message(
                KafkaTopics.CHARGING_SESSION_COMPLETE, completion_message
            )
            self.logger.info(
                f"Charging completion sent to Kafka: {completion_message['session_id']}"
            )
        else:
            self.logger.warning(
                "Kafka manager not initialized, skipped sending charging completion."
            )

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

        try:

            self.running = True
            while self.running:
                time.sleep(1)  # 保持运行

        except KeyboardInterrupt:
            self.logger.info("Shutting down EV_CP_E")
            self._shutdown_system()
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self._shutdown_system()


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    ev_cp_e = EV_CP_E(logger=logger)
    ev_cp_e.start()
