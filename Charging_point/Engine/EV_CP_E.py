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
from Common.Config.ConsolePrinter import get_printer
from Common.Database.SqliteConnection import SqliteConnection
from Common.Database.ChargingSessionRepository import ChargingSessionRepository


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
            self.tools.add_argument(
                "--debug_port",
                type=int,

                help="Puerto para el modo debug (predeterminado: 5004)"
            )
            self.args = self.tools.parse_args()

            # 非 debug 模式：从 .env 文件读取监听端口，如果没有则使用端口 0（自动分配）
            if not self.args.debug_port:
                # config.get_ip_port_ev_cp_e() 返回 tuple: (host, port)
                self.engine_listen_address = self.config.get_ip_port_ev_cp_e()
                self.logger.info(f"Using listen address from .env: {self.engine_listen_address[0]}:{self.engine_listen_address[1]}")
            else:
                # debug_port 参数提供，使用 localhost
                self.engine_listen_address = ("localhost", self.args.debug_port)
                self.logger.info(f"Using debug port from command line: {self.args.debug_port}")
        else:

            class Args:
                broker = self.config.get_broker()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

            # debug 模式：从配置文件读取Engine监听地址
            self.engine_listen_address = self.config.get_ip_port_ev_cp_e()

        self.running = False
        self.monitor_server: MySocketServer = None
        self.kafka_manager: KafkaManager = None  # Kafka manager

        self.current_session = None

        self.cp_id = None
        self._id_initialized = False

        # Flag para simular fallo manual (usado por CLI)
        # Cuando está en True, get_current_status() siempre retorna FAULTY
        self._manual_faulty_mode = False

        # Flag para indicar que el CP está en estado STOPPED (servicio suspendido por administrador)
        # Cuando está en True, no se pueden iniciar nuevas sesiones de carga
        self.cp_service_stopped = False

        # Sesión de recarga suspendida por avería (se guarda temporalmente)
        # Cuando el Engine entra en estado FAULTY durante una recarga, la sesión se guarda aquí
        # para enviarla a Central y Driver cuando el Engine vuelva a estar ACTIVE
        self._suspended_session = None

        self.message_dispatcher = EngineMessageDispatcher(self.logger, self)
        self.engine_cli = None  # CLI para simular acciones del usuario (enchufar/desenchufar vehículo)
        self.printer = get_printer()  # 使用美化输出工具

        # 数据库连接和仓库 - 用于持久化挂起的充电会话
        self.db_connection = None
        self.session_repository = None
        self._init_database()

    def _init_database(self):
        """初始化数据库连接和仓库"""
        try:
            # 数据库文件路径
            db_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "charging_sessions_engine.db"
            )
            schema_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "Core", "BD", "table.sql"
            )

            # 确保data目录存在
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

            # 初始化数据库连接
            # 注意: Engine使用独立的数据库,只用于会话恢复
            # 不需要外键约束检查,因为不涉及其他表的关联
            self.db_connection = SqliteConnection(
                db_path=db_path,
                sql_schema_file=schema_path,
                create_tables_if_not_exist=True
            )

            # 禁用外键约束,因为Engine的数据库是独立的
            # 只用于保存和恢复挂起的会话,不涉及完整的数据关联
            conn = self.db_connection.get_connection()
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.commit()

            # 初始化会话仓库
            self.session_repository = ChargingSessionRepository(
                self.db_connection
            )

            self.logger.debug("Engine database initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Engine database: {e}")
            self.db_connection = None
            self.session_repository = None

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

        # 如果之前有旧的CP_ID（Monitor断开重连的情况），记录变化
        if self.cp_id is not None and self.cp_id != cp_id:
            self.logger.debug(f"CP_ID changed from {self.cp_id} to {cp_id}")

        self.cp_id = cp_id
        self._id_initialized = True
        self.logger.debug(f"CP_ID initialized: {self.cp_id}")
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
        """
        处理Monitor断开连接

        Monitor断开意味着失去了通信和监控能力，必须立即停止充电并结束会话。
        这与Engine断开不同 - Engine断开时会话可以等待恢复，但Monitor断开必须结束。
        """
        self.logger.warning(f"Monitor {client_id} disconnected")
        if self.is_charging:
            self.logger.warning(
                "Monitor disconnected during charging - stopping charging and sending completion"
            )
            # Monitor断开时，立即停止充电并发送ticket
            # 这是正常的充电结束流程，不是挂起
            self._stop_charging_session()

        self._id_initialized = False
        self.logger.debug("CP_ID reset - new Monitor can now initialize with a different ID")



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

            actual_port = self.monitor_server.get_actual_port()
            actual_host = self.engine_listen_address[0]

            self.engine_listen_address = (actual_host, actual_port)

            self.logger.debug(
                f"Monitor server started on {actual_host}:{actual_port}"
            )

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

                self.logger.debug("Kafka producer initialized successfully")
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
        self.logger.debug("Starting system shutdown...")
        self.running = False

        # 如果正在充电,保存会话到数据库而不是停止
        if self.is_charging:
            self.logger.info("Charging session detected during shutdown - saving to database for recovery")
            self._suspend_current_session_to_database()
            # 清除当前会话但不发送完成通知
            self.current_session = None


        if self.engine_cli:
            self.engine_cli.stop()

        if self.monitor_server:
            self.monitor_server.stop()

        if self.kafka_manager:
            self.kafka_manager.stop()

        self.logger.debug("System shutdown complete")

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
            "energy_consumed_kwh": 0.0,  
            "total_cost": 0.0,  
            "price_per_kwh": price_per_kwh,  
        }
        # Start charging thread
        charging_thread = threading.Thread(
            target=self._charging_process,
            args=(session_id,),
            daemon=True, 
        )
        charging_thread.start()
        self.logger.debug(
            f"Charging session {self.current_session['session_id']} "
        )
        return True

    def _stop_charging_session(self, force_stop=False):
        """
        停止充电会话。

        Args:
            force_stop: Si es True, finaliza completamente la sesión aunque esté en FAULTY.
                       Si es False y está en FAULTY, guarda la sesión temporalmente.

        因为一个ChargingPoint只能有一个充电会话。
        """
        self.logger.info(f"Stopping charging for session {self.current_session['session_id']}... ")
        if not self.is_charging:
            self.logger.warning("No active charging session to stop.")
            return False

        session_id = self.current_session["session_id"]
        driver_id = self.current_session["driver_id"]
        self.logger.info(f"Stopping charging session '{session_id}' for Driver: {driver_id}")

        final_session_data = self.current_session.copy()
        final_session_data["end_time"] = time.time()
        final_session_data["duration"] = (
            final_session_data["end_time"] - final_session_data["start_time"]
        )

        # Si el Engine está en modo FAULTY y no es un force_stop,
        # guardar la sesión temporalmente en lugar de finalizarla
        if self._manual_faulty_mode and not force_stop:
            self.logger.warning(f"⚠️  Engine is FAULTY - Suspending session '{session_id}' temporarily")
            self.logger.info(f"Session will be completed and sent when Engine recovers")

            # Enviar mensaje de error al Driver informando de la avería
            self._send_fault_notification_to_driver(driver_id, session_id, final_session_data)

            self._suspended_session = final_session_data
            self.current_session = None
            return True

        # 准备ticket数据
        ticket_data = {
            "session_id": session_id,
            "cp_id": self.cp_id if self.cp_id else "N/A",
            "driver_id": driver_id,
            "energy_consumed_kwh": final_session_data['energy_consumed_kwh'],
            "total_cost": final_session_data['total_cost'],
            "start_time": final_session_data.get("start_time"),
            "end_time": final_session_data["end_time"],
        }

        self.current_session = None

        # 使用Rich美化显示充电完成票据
        self.printer.print_charging_ticket(ticket_data)

        self._send_charging_completion(final_session_data)  # Send completion notification
        return True

    def _charging_process(self, session_id_to_track: str):
        """充电过程模拟（30秒后自动停止）"""
        self.logger.debug(f"Charging process started for session {session_id_to_track}.")


        charging_start_time = time.time()
        MAX_CHARGING_DURATION = self.config.get_max_charging_duration()

 
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

                # Check if 30 seconds of charging have elapsed
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
                self._send_charging_data()  # Send charging data to Monitor and Kafka
                self.logger.debug(
                    f"Session {session_id_to_track} progress: {self.current_session['energy_consumed_kwh']:.3f} kWh, €{self.current_session['total_cost']:.2f}, elapsed: {elapsed_time:.1f}s/{MAX_CHARGING_DURATION}s"
                )
            except Exception as e:
                self.logger.error(
                    f"Error in charging process for session {session_id_to_track}: {e}"
                )
                break
        self.logger.debug(f"Charging process ended for session {session_id_to_track}.")

    def _send_charging_data(self):
        """发送充电数据到Monitor和Kafka"""
        if not self.current_session:  # 如果没有活跃会话，直接返回
            return

        charging_data_message = {
            "type": "charging_data",
            "message_id": str(uuid.uuid4()),  
            "cp_id": self.cp_id,  
            "session_id": self.current_session["session_id"],
            "driver_id": self.current_session.get("driver_id", "unknown"),  # 添加driver_id用于Monitor显示
            "energy_consumed_kwh": round(
                self.current_session["energy_consumed_kwh"], 3
            ),
            "total_cost": round(self.current_session["total_cost"], 2),
            "timestamp": int(time.time()),
        }

        if self.monitor_server and self.monitor_server.has_active_clients():
            self.monitor_server.send_broadcast_message(charging_data_message)
            self.logger.debug(
                f"Charging data sent to Monitor: {charging_data_message['session_id']}"
            )
        else:
            self.logger.debug("No active monitor clients to send charging data.")

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
            "message_id": str(uuid.uuid4()),
            "cp_id": self.cp_id,
            "session_id": final_session_data["session_id"],
            "energy_consumed_kwh": round(final_session_data["energy_consumed_kwh"], 3),
            "total_cost": round(final_session_data["total_cost"], 2),
            "timestamp": int(time.time()),
        }

        if self.monitor_server and self.monitor_server.has_active_clients():
            self.monitor_server.send_broadcast_message(completion_message)
            self.logger.info(
                f"Charging completion sent to Monitor: {completion_message['session_id']}"
            )
        else:
            self.logger.debug(
                "No active monitor clients to send charging completion."
            )

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

    def _send_fault_notification_to_driver(self, driver_id: str, session_id: str, session_data: dict):
        """
        Envía notificación de avería al Driver cuando el Engine falla durante una recarga.

        Args:
            driver_id: ID del conductor
            session_id: ID de la sesión de recarga
            session_data: Datos de la sesión al momento de la avería
        """
        if not self.kafka_manager or not self.kafka_manager.is_connected():
            self.logger.warning(f"Cannot send fault notification to Driver {driver_id} - Kafka not available")
            return

        fault_message = {
            "type": "charging_status_update",
            "message_id": str(uuid.uuid4()),
            "driver_id": driver_id,
            "session_id": session_id,
            "cp_id": self.cp_id,
            "status": "error",
            "message": f"⚠️  Charging Point has experienced a FAULT. Charging session suspended.",
            "reason": "CP_ENGINE_FAULT",
            "energy_consumed_kwh": round(session_data['energy_consumed_kwh'], 3),
            "total_cost": round(session_data['total_cost'], 2),
            "timestamp": int(time.time()),
        }

        success = self.kafka_manager.produce_message(
            KafkaTopics.DRIVER_RESPONSES, fault_message
        )

        if success:
            self.logger.info(f"✓  Fault notification sent to Driver {driver_id} via Kafka")
            self.printer.print_warning(f"Driver {driver_id} notified about Engine failure")
        else:
            self.logger.error(f"Failed to send fault notification to Driver {driver_id}")

    def _suspend_current_session_to_database(self):
        """
        将当前充电会话保存到数据库。

        当Engine关闭时调用此方法。会话数据完全保存到数据库中，
        下次Engine启动并连接Monitor时会自动恢复。
        """
        if not self.current_session:
            self.logger.warning("No active session to suspend")
            return

        session_id = self.current_session["session_id"]
        self.logger.info(f"💾 Saving charging session '{session_id}' to database...")

        # 保存会话快照(包含当前充电进度)
        session_snapshot = self.current_session.copy()

        # 保存到数据库
        if self.session_repository:
            try:
                # 更新或创建数据库记录
                if self.session_repository.exists(session_id):
                    # 更新现有记录
                    self.session_repository.update(
                        session_id=session_id,
                        energy_consumed_kwh=session_snapshot["energy_consumed_kwh"],
                        total_cost=session_snapshot["total_cost"],
                        price_per_kwh=session_snapshot.get("price_per_kwh", 0.2),
                        status="suspended"  # 标记为挂起状态
                    )
                    self.logger.info(f"✓ Session '{session_id}' updated in database (suspended)")
                else:
                    # 创建新记录
                    self.session_repository.create(
                        session_id=session_id,
                        cp_id=self.cp_id if self.cp_id else "N/A",
                        driver_id=session_snapshot["driver_id"],
                        start_time=session_snapshot["start_time"],
                        price_per_kwh=session_snapshot.get("price_per_kwh", 0.2)
                    )
                    self.session_repository.update(
                        session_id=session_id,
                        energy_consumed_kwh=session_snapshot["energy_consumed_kwh"],
                        total_cost=session_snapshot["total_cost"],
                        status="suspended"
                    )
                    self.logger.info(f"✓ Session '{session_id}' saved to database (suspended)")

                self.logger.info(
                    f"Session '{session_id}' persisted - "
                    f"Energy: {session_snapshot['energy_consumed_kwh']:.3f} kWh, "
                    f"Cost: €{session_snapshot['total_cost']:.2f}"
                )
                self.printer.print_warning(
                    f"Session '{session_id}' saved to database. "
                    f"Will resume when Engine restarts and Monitor reconnects."
                )
            except Exception as e:
                self.logger.error(f"Failed to save session to database: {e}")
                self.printer.print_error(f"Could not save session to database: {e}")
        else:
            self.logger.error("Session repository not available - cannot save session!")
            self.printer.print_error("Database not available - session will be lost!")


    def _recover_suspended_session_on_reconnect(self):
        """
        当Monitor重连时恢复挂起的充电会话。

        恢复流程:
        1. 从数据库加载挂起的会话数据(status='suspended')
        2. 恢复会话到current_session
        3. 重启充电进程线程
        """
        if not self.session_repository or not self.cp_id:
            self.logger.debug("Session repository or CP_ID not available - cannot recover sessions")
            return

        suspended_session = None

        try:
            # 从数据库查找此充电桩的挂起会话
            all_sessions = self.session_repository.get_sessions_by_charging_point(self.cp_id)

            # 查找状态为"suspended"的会话
            for session in all_sessions:
                if session.get("status") == "suspended":
                    suspended_session = session
                    self.logger.info(f"Found suspended session in database: {session['session_id']}")
                    break
        except Exception as e:
            self.logger.error(f"Failed to query database for suspended sessions: {e}")
            return

        if not suspended_session:
            self.logger.debug("No suspended session found to recover")
            return

        session_id = suspended_session["session_id"]
        self.logger.info(f"🔄 Recovering suspended session '{session_id}'...")

        # 从数据库恢复会话数据
        energy = suspended_session.get("energy_consumed_kwh", 0.0)
        cost = suspended_session.get("total_cost", 0.0)
        # 优先使用数据库中保存的price_per_kwh,如果没有则从cost和energy反推,或使用默认值
        price_per_kwh = suspended_session.get("price_per_kwh")
        if price_per_kwh is None:
            price_per_kwh = (cost / energy) if energy > 0 else 0.2  # 默认€0.2/kWh

        # 恢复会话到current_session
        self.current_session = {
            "session_id": suspended_session["session_id"],
            "driver_id": suspended_session["driver_id"],
            "start_time": suspended_session["start_time"],
            "energy_consumed_kwh": energy,
            "total_cost": cost,
            "price_per_kwh": price_per_kwh,
        }

        # 重启充电进程线程
        charging_thread = threading.Thread(
            target=self._charging_process,
            args=(session_id,),
            daemon=True,
        )
        charging_thread.start()

        # 更新数据库状态为进行中
        try:
            self.session_repository.update(
                session_id=session_id,
                status="in_progress"  # 恢复为进行中
            )
            self.logger.info(f"✓ Database status updated to 'in_progress'")
        except Exception as e:
            self.logger.error(f"Failed to update session status in database: {e}")

        self.logger.info(
            f"✓ Session '{session_id}' recovered and resumed - "
            f"Energy: {self.current_session['energy_consumed_kwh']:.3f} kWh, "
            f"Cost: €{self.current_session['total_cost']:.2f}, "
            f"Price: €{price_per_kwh:.2f}/kWh"
        )
        self.printer.print_success(
            f"Session '{session_id}' resumed after Engine restart"
        )

    def _resume_suspended_session(self):
        """
        Envía la sesión suspendida cuando el Engine se recupera de FAULTY.

        Este método se llama cuando el Engine vuelve a estar ACTIVE después de una avería.
        Envía los datos de la sesión suspendida a Central (vía Kafka) y a Driver.
        """
        if not self._suspended_session:
            return

        self.logger.info(f"✓  Engine recovered - Processing suspended session '{self._suspended_session['session_id']}'")

        # Preparar ticket data para mostrar al usuario
        ticket_data = {
            "session_id": self._suspended_session["session_id"],
            "cp_id": self.cp_id if self.cp_id else "N/A",
            "driver_id": self._suspended_session["driver_id"],
            "energy_consumed_kwh": self._suspended_session['energy_consumed_kwh'],
            "total_cost": self._suspended_session['total_cost'],
            "start_time": self._suspended_session.get("start_time"),
            "end_time": self._suspended_session["end_time"],
        }

        # Mostrar el ticket de la sesión finalizada
        self.printer.print_charging_ticket(ticket_data)
        self.printer.print_success(f"Suspended session '{self._suspended_session['session_id']}' completed after recovery")

        # Enviar los datos de finalización a Central y Driver
        self._send_charging_completion(self._suspended_session)

        # Limpiar la sesión suspendida
        self._suspended_session = None
        self.logger.info("Suspended session processed successfully")

    def _init_cli(self):
        """初始化Engine CLI"""
        try:
            self.engine_cli = EngineCLI(self, self.logger)
            self.engine_cli.start()
            self.logger.debug("Engine CLI initialized successfully")
            self.logger.debug("Press ENTER to show interactive menu for manual operations")
        except Exception as e:
            self.logger.error(f"Failed to initialize Engine CLI: {e}")
            self.engine_cli = None

    def initialize_system(self):
        """初始化系统"""
        self.logger.debug("Initializing EV_CP_E module")
        return self._init_connections()

    def start(self):
        self.logger.debug(
            f"Will listen for Monitor on {self.engine_listen_address[0]}:{self.engine_listen_address[1]}"
        )
        self.logger.debug(
            f"Will connect to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )

        if not self.initialize_system():
            self.logger.error("Failed to initialize system")
            sys.exit(1)

        
        self._init_cli()

        try:

            self.running = True
            while self.running:
                time.sleep(0.1)  # Keep running

        except KeyboardInterrupt:
            self.logger.debug("Shutting down EV_CP_E")
            self._shutdown_system()
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self._shutdown_system()


if __name__ == "__main__":
    import logging
    config = ConfigManager()
    debug_mode = config.get_debug_mode()
    if not debug_mode:
        logger = CustomLogger.get_logger(level=logging.INFO)
    else:
        logger = CustomLogger.get_logger(level=logging.DEBUG)
    ev_cp_e = EV_CP_E(logger=logger)
    ev_cp_e.start()
