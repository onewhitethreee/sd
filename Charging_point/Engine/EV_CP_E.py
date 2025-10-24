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
        self.message_handlers = {
            "health_check_request": self._handle_health_check,
            "stop_command": self._handle_stop_command,
            "resume_command": self._handle_resume_command,
            "start_charging_command": self._handle_start_charging_command,
        }

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
        # 消息已经是字典格式（JSON）
        try:
            msg_type = message.get("type")
            self.logger.debug(f"Received message from Monitor {client_id}: {msg_type}")

            handler = self.message_handlers.get(msg_type)
            if handler:
                return handler(message)
            else:
                self.logger.warning(f"Unknown message type from Monitor: {msg_type}")
                return {
                    "type": "error_response",
                    "message_id": message.get("message_id"),
                    "error": "Unknown message type",
                }

        except Exception as e:
            self.logger.error(f"Error processing monitor message: {e}")
            return {
                "type": "error_response",
                "message_id": message.get("message_id"),
                "error": str(e),
            }

    def _handle_health_check(self, message):
        """处理健康检查请求"""

        response = {
            "type": "health_check_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "engine_status": self.get_current_status(),
            "timestamp": int(time.time()),
            "is_charging": self.is_charging,
        }

        self.logger.debug(f"Health check response prepared {response}")
        return response

    def _handle_stop_command(self, message):
        """处理停止命令"""
        self.logger.info("Received stop command from Monitor")

        if self.is_charging:
            self._stop_charging_session(ev_id=None)

        response = {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "message": "Stop command executed",
        }
        return response

    def _handle_resume_command(self, message):
        """处理恢复命令"""
        self.logger.info("Received resume command from Monitor")
        # 实际的恢复逻辑可能更复杂，这里仅重置状态
        if not self.running:  # 假设 resume 意味着重新启动主循环（如果它停止了）
            self.running = True
            self.logger.info("Engine resumed operation")
        return {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "message": "Resume command executed",
        }

    def _handle_start_charging_command(self, message):
        """处理开始充电命令"""
        self.logger.info("Received start charging command from Monitor")

        ev_id = message.get("ev_id", "unknown_ev")

        if self.is_charging:
            return {
                "type": "command_response",
                "message_id": message.get("message_id"),
                "status": "failure",
                "message": "Already charging",
                "session_id": self.current_session["session_id"],  # 返回当前session ID
            }
        session_id = str(uuid.uuid4())  # Engine 自己生成 ID
        success = self._start_charging_session(ev_id, session_id)
        return {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success" if success else "failure",
            "message": "Charging started" if success else "Failed to start charging",
            "session_id": session_id if success else None,
        }

    def _handle_monitor_disconnect(self, client_id):
        """处理Monitor断开连接"""
        self.logger.warning(f"Monitor {client_id} disconnected")
        # 进入安全模式：停止当前充电会话
        if self.is_charging:
            self.logger.warning(
                "Monitor disconnected during charging - stopping charging for safety"
            )
            self._stop_charging_session()  # 移除 ev_id 参数

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
        try:
            broker_address = f"{self.args.broker[0]}:{self.args.broker[1]}"
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
            self._stop_charging_session(ev_id=None)
            self.is_charging = False

        if self.monitor_server:
            self.monitor_server.stop()  # 使用现有的stop()方法

        if self.kafka_manager:
            self.kafka_manager.stop()

        self.logger.info("System shutdown complete")

    def _start_charging_session(self, ev_id: str, session_id: str):
        """启动充电会话。Engine 自己生成 session_id。"""
        self.logger.info(f"Starting charging session '{session_id}' for EV: {ev_id}")
        if self.is_charging:
            self.logger.warning("Already charging, cannot start new session.")
            return False
        # --- 重点：所有会话数据都在 current_session 里 ---
        self.current_session = {
            "session_id": session_id,
            "ev_id": ev_id,
            "start_time": time.time(),
            "energy_consumed_kwh": 0.0,  # 初始能量
            "total_cost": 0.0,  # 初始费用
            "charging_rate_kw": random.uniform(5.0, 22.0),  # 定义：这是千瓦 (kW)
            "price_per_kwh": 0.20,  # 每千瓦时价格
        }
        # 启动充电线程
        # 注意：这里如果 charging_thread 已经结束，但 self.is_charging 为 True
        # 需要确保线程可以被安全地重新赋值或等待。更好的做法是确保 _charging_process 不会死循环。
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
        """停止充电会话。不再需要 ev_id 参数。"""
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
            "charging_rate": round(self.current_session["charging_rate_kw"], 1),
        }
        # --- 重点：使用 MySocketServer 的新广播 API ---
        if self.monitor_server and self.monitor_server.has_active_clients():
            self.monitor_server.send_broadcast_message(
                charging_data_message
            )  # 使用新的 API
            self.logger.debug(
                f"Charging data sent to Monitor: {charging_data_message['session_id']}"
            )
        else:
            self.logger.debug("No active monitor clients to send charging data.")
        # --- 重点：发送到 Kafka ---
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
        # --- 重点：使用 MySocketServer 的新广播 API ---
        if self.monitor_server and self.monitor_server.has_active_clients():
            self.monitor_server.send_broadcast_message(
                completion_message
            )  # 使用新的 API
            self.logger.info(
                f"Charging completion sent to Monitor: {completion_message['session_id']}"
            )
        else:
            self.logger.warning(
                "No active monitor clients to send charging completion."
            )
        # --- 重点：发送到 Kafka ---
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
        self.logger.info("Starting EV_CP_E module")
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
            # 启动交互式命令处理线程
            command_thread = threading.Thread(
                target=self._interactive_commands, daemon=True
            )
            command_thread.start()

            while self.running:
                time.sleep(1)  # 保持运行

        except KeyboardInterrupt:
            self.logger.info("Shutting down EV_CP_E")
            self._shutdown_system()
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self._shutdown_system()

    def _interactive_commands(self):
        """交互式命令处理"""
        self.logger.info("\n--- Interactive commands available (DEBUG MODE) ---")
        self.logger.info("  - Press 'c' + Enter to simulate a Monitor connection")
        self.logger.info("  - Press 'd' + Enter to simulate a Monitor disconnect")
        self.logger.info("  - Press 's' + Enter to start charging (manual_ev)")
        self.logger.info("  - Press 'e' + Enter to end charging")
        self.logger.info("  - Press 'q' + Enter to quit")
        self.logger.info("---------------------------------------------------\n")
        while self.running:
            try:
                command = input().strip().lower()
                if command == "q":
                    self.logger.info("Quit command received.")
                    self.running = False
                    break
                elif command == "c":
                    self.logger.info("Simulating Monitor connection...")
                    # 模拟 Monitor 连接，客户端ID为 'test_monitor'
                    if self.monitor_server:
                        self.monitor_server._simulate_client_connect("test_monitor")
                    else:
                        self.logger.warning("Monitor server not running.")
                elif command == "d":
                    self.logger.info("Simulating Monitor disconnection...")
                    # 模拟 Monitor 断开
                    if self.monitor_server:
                        self.monitor_server._simulate_client_disconnect("test_monitor")
                    else:
                        self.logger.warning("Monitor server not running.")

                elif command == "s":
                    if not self.is_charging:
                        session_id = str(uuid.uuid4())  # 手动模式也创建会话ID
                        self._start_charging_session("manual_ev", session_id)
                        self.logger.info(
                            f"Manual charging session '{session_id}' started."
                        )
                    else:
                        self.logger.info(
                            f"Already charging session '{self.current_session['session_id']}'."
                        )
                elif command == "e":
                    if self.is_charging:
                        self._stop_charging_session()
                        self.logger.info("Manual charging stopped.")
                    else:
                        self.logger.info("No active charging session to stop.")
                else:
                    self.logger.info(
                        "Unknown command. Use 'c' connect, 'd' disconnect, 's' start, 'e' end, 'q' quit"
                    )
            except EOFError:
                # 处理输入结束，比如管道关闭
                self.logger.info(
                    "EOF received in interactive commands. Exiting command thread."
                )
                break
            except Exception as e:
                self.logger.error(f"Error in interactive commands: {e}", exc_info=True)
                break


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    ev_cp_e = EV_CP_E(logger=logger)
    ev_cp_e.start()
