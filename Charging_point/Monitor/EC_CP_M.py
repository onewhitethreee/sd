"""
Módulo que monitoriza la salud de todo el punto de recarga y que reporta a la CENTRAL cualquier avería de este. Sirve igualmente para autenticar y registrar a los CP en la central cuando sea oportuno.
"""

import sys
import os
import uuid
import time
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager
from Common.MySocketClient import MySocketClient


class EV_CP_M:
    def __init__(self, logger=None):
        self.logger = logger
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()
        if not self.debug_mode:
            self.tools = AppArgumentParser(
                "EV_CP_M", "Módulo de monitorización del punto de recarga"
            )
            self.tools.add_argument(
                "ip_port_ev_cp_e",
                type=ip_port_type,
                help="IP y puerto del EV_CP_E (formato IP:PORT)",
            )
            self.tools.add_argument(
                "ip_port_ev_central",
                type=ip_port_type,
                help="IP y puerto del EV_CP_Central (formato IP:PORT)",
            )
            self.tools.add_argument(
                "id_cp", type=str, help="Identificador único del punto de recarga"
            )
            self.args = self.tools.parse_args()
        else:

            class Args:
                ip_port_ev_cp_e = self.config.get_ip_port_ev_cp_e()
                ip_port_ev_central = self.config.get_ip_port_ev_cp_central()
                id_cp = self.config.get_id_cp()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")
        self.central_client = None  # Cliente para conectar con EV_Central
        self.engine_client = None  # Servidor para aceptar conexiones de EV_CP_E
        self.running = False
        self.RETRY_INTERVAL = 5  # Intervalo de reintento en segundos
        self.threads = []

    def _connect_to_central(self):
        """
        连接到EV_Central
        """
        self.central_client = MySocketClient(
            logger=self.logger,
            message_callback=self._handle_central_message,
        )
        return self.central_client.connect(
            self.args.ip_port_ev_central[0], self.args.ip_port_ev_central[1]
        )

    def _handle_disconnection(self):
        """
        处理断开连接和重试机制
        """
        pass

    def _register_with_central(self):
        """
        和central注册一个charging point
        """
        register_message = {
            "type": "register_request",
            "message_id": str(uuid.uuid4()),
            "id": self.args.id_cp,
            "location": "Location_Info",  # 可以是一个字符串，表示位置
            "price_per_kwh": 0.20,  # 每千瓦时的价格
        }
        return self.central_client.send(register_message)

    def _send_heartbeat(self):
        """
        发送心跳消息以保持与中央的连接
        """
        while self.running:
            if self.central_client and self.central_client.is_connected:
                heartbeat_msg = {
                    "type": "heartbeat_request",
                    "message_id": str(uuid.uuid4()),
                    "id": self.args.id_cp,
                }
                if self.central_client.send(heartbeat_msg):
                    self.logger.debug("Heartbeat sent")
                else:
                    self.logger.error("Failed to send heartbeat")
            time.sleep(30)  # Cada 30 segundos enviar un latido
        self.logger.info("theartbeat thread has stopped")

    def _start_heartbeat_thread(self):
        """
        启动发送心跳的线程
        """
        heartbeat_thread = threading.Thread(target=self._send_heartbeat, daemon=False)
        heartbeat_thread.start()
        self.threads.append(heartbeat_thread)

    def autheticate_charging_point(self):
        """
        认证充电点
        """
        pass

    def _connect_to_engine(self):
        """
        连接到EV_CP_E
        """
        self.engine_client = MySocketClient(
            logger=self.logger,
            message_callback=self._handle_engine_message,
        )
        return self.engine_client.connect(
            self.args.ip_port_ev_cp_e[0], self.args.ip_port_ev_cp_e[1]
        )

    def _check_engine_health(self):
        """
        检查EV_CP_E的健康状态
        """
        self.logger.info("Starting health check thread for EV_CP_E")
        
        while self.running:
            try:
                if not self.engine_client or not self.engine_client.is_connected:
                    self.logger.info("Connecting to EV_CP_E...")
                    if not self._connect_to_engine():
                        self.logger.error("Failed to connect to EV_CP_E")
                        self._report_failure("EV_CP_E connection failed") 
                        time.sleep(self.RETRY_INTERVAL)
                        continue

                health_check_msg = {
                    "type": "health_check_request",
                    "message_id": str(uuid.uuid4()),
                    "id": self.args.id_cp,
                    "timestamp": int(time.time()),
                }
                if self.engine_client.send(health_check_msg):
                    self.logger.debug("Health check sent to EV_CP_E")
                else:
                    self.logger.error("Failed to send health check to EV_CP_E")
                    self._report_failure("Health check send failed")  
                    
            except Exception as e:
                self.logger.error(f"Error checking EV_CP_E health: {e}")
                self._report_failure(f"Health check error: {str(e)}")

            time.sleep(60) # TODO 每60秒检查一次, production 可能需要更频繁
        
        self.logger.info("Health check thread for EV_CP_E has stopped")


    def _report_failure(self, failure_info):
        """
        向central报告故障
        """
        failure_message = {
            "type": "fault_notification",
            "message_id": str(uuid.uuid4()),
            "id": self.args.id_cp,
            "failure_info": failure_info,
        }
        if self.central_client and self.central_client.is_connected:
            if self.central_client.send(failure_message):
                self.logger.info("Reported failure to central")
            else:
                self.logger.error("Failed to report failure to central")

    def _check_status(self):
        """
        检查充电点的状态
        """
        pass

    def update_cp_status(self, status):
        """
        更新充电点状态
        """
        pass

    def report_status_to_central(self, status):
        """
        向central报告状态
        """
        pass

    def _handle_engine_message(self, message):
        """
        处理来自EV_CP_E的消息
        """
        message_type = message.get("type")
        if message_type == "health_check_response":
            self.logger.debug(f"Health check response from EV_CP_E: {message}")
            # TODO 处理健康检查响应
        elif message_type == "SERVER_SHUTDOWN":
            self.logger.warning("EV_CP_E server is shutting down")
            self._handle_server_shutdown()
        elif message_type == "CONNECTION_ERROR":
            self.logger.error(f"Connection error from EV_CP_E: {message}")
        else:
            self.logger.warning(f"Unknown message type from EV_CP_E: {message_type}")

    def _handle_central_message(self, message):
        """
        处理来自central的消息
        """
        message_type = message.get("type")
        if message_type == "register_response":
            self.logger.info("Received registration response from central")
            self.logger.debug(f"Registration response details: {message}")
            # TODO 这里需要用MessageFormatter来进行解包和验证
            # TODO 不需要解包，通过debug发现MySocketClient已经为我们处理好了
            if message.get("status") == "success":
                self.logger.info("Registration successful")
                # TODO 处理注册成功后的逻辑

        elif message_type == "heartbeat_response":
            self.logger.debug("Received heartbeat response from central")
            if message.get("status") == "success":
                self.logger.debug(f"Heartbeat acknowledged by central {message}")
            else:
                self.logger.warning(f"Heartbeat not acknowledged by central {message}")

        elif message_type == "SERVER_SHUTDOWN":
            self.logger.warning("Central server is shutting down")
            self._handle_server_shutdown()

        elif message_type == "CONNECTION_ERROR":
            self.logger.error(f"Connection error from central: {message}")

        else:
            self.logger.warning(f"Unknown message type from central: {message_type}")

    def _handle_server_shutdown(self):
        self.logger.info("Initiating graceful shutdown due to central server shutdown")
        threading.Thread(target=self._graceful_shutdown, daemon=False).start()

    def _graceful_shutdown(self):
        """
        Realiza un cierre ordenado del sistema
        """
        # Dar tiempo para terminar operaciones pendientes
        time.sleep(2)

        # Detener loops activos
        self.running = False
        
        self.logger.info(f"Waiting for threads to finish... {len(self.threads)} threads")
        for thread in self.threads:
            thread.join(timeout=5)
            if thread.is_alive():
                self.logger.warning(f"Thread {thread.name} did not finish in time")
        self.logger.info("All threads have been stopped")

        # Desconectar clientes
        if self.central_client:
            self.central_client.disconnect()
        if self.engine_client:
            self.engine_client.disconnect()

        # Cerrar otros recursos si los hay
        # TODO: Cerrar servidor para EV_CP_E cuando esté implementado

        self.logger.info("Shutdown complete")
    def _retry_connection(self):
        """
        重试连接到central
        """
        retry_count = 0
        max_retries = 10

        while self.running and retry_count < max_retries:
            retry_count += 1
            self.logger.info(f"Connection retry to central {retry_count}/{max_retries}")

            if self._connect_to_central():
                self.logger.info("Reconnected to EV_Central")
                return True

            self.logger.error(f"Connection failed, waiting {self.RETRY_INTERVAL}s...")
            time.sleep(self.RETRY_INTERVAL)

        self.logger.error(f"Connection failed after {max_retries} attempts")
        return False

    def _retry_registration(self):
        """
        重试注册机制
        """
        retry_count = 0
        max_retries = 5

        while self.running and retry_count < max_retries:
            retry_count += 1
            self.logger.info(f"Registration retry {retry_count}/{max_retries}")

            if self._register_with_central():
                self.logger.info("Registration successful")
                self._start_heartbeat_thread()
                return True

            self.logger.error(f"Registration failed, waiting {self.RETRY_INTERVAL}s...")
            time.sleep(self.RETRY_INTERVAL)

        self.logger.error(f"Registration failed after {max_retries} attempts")
        return False
    def _ensure_connection_and_registration(self):
        """
        确保连接和注册
        """
        self.logger.info("Ensuring connection and registration with EV_Central")
        # Primero asegurar conexión
        if not self.central_client or not self.central_client.is_connected:
            if not self._retry_connection():
                return False

        # Luego asegurar registro
        return self._retry_registration()

    def initialize_systems(self):
        """
        初始化系统，连接到central和EV_CP_E
        """
        if self._connect_to_central():
            self.logger.info("Connected to EV_Central")
            if self._register_with_central():
                self.logger.info("Registration message sent to central")
                self._start_heartbeat_thread()
            else:
                self.logger.error("Failed to send registration message to EV_Central")
                retry_thread = threading.Thread(target=self._ensure_connection_and_registration, daemon=False)
                self.threads.append(retry_thread)
                retry_thread.start()
        else:
            self.logger.error("Failed to connect to EV_Central")
            ensure_thread = threading.Thread(target=self._ensure_connection_and_registration, daemon=False)
            self.threads.append(ensure_thread)
            ensure_thread.start()
        if self._connect_to_engine():
            self.logger.info("Connected to EV_CP_E")
        else:
            self.logger.error("Failed to connect to EV_CP_E")

        # 启动检查EV_CP_E健康状态的线程
        health_thread = threading.Thread(target=self._check_engine_health, daemon=False)
        self.threads.append(health_thread)
        health_thread.start()

    def start(self):
        self.running = True
        self.logger.info(f"Starting EV_CP_M module")
        self.logger.info(
            f"Listening  to EV_CP_E at {self.args.ip_port_ev_cp_e[0]}:{self.args.ip_port_ev_cp_e[1]}"
        )
        self.logger.info(
            f"Connecting to EV_Central at {self.args.ip_port_ev_central[0]}:{self.args.ip_port_ev_central[1]}"
        )
        self.logger.info(f"Point ID: {self.args.id_cp}")

        self.initialize_systems()

        # Aquí iría la lógica para iniciar el módulo, conectar al broker, leer sensores, etc.
        try:
            while self.running:
                time.sleep(1)  # Simulación de la ejecución continua del servicio
                # self.logger.debug(f"EV_CP_M is running... {self.running}")
        except KeyboardInterrupt:
            self.logger.info("Shutting down EV CP M")
            self._graceful_shutdown()
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self._graceful_shutdown()
        finally:
            self.logger.info("EV_CP_M has stopped")
            os._exit(0)  # Asegura que el proceso termina


if __name__ == "__main__":
    logger = CustomLogger.get_logger()

    ev_cp_m = EV_CP_M(logger=logger)
    ev_cp_m.start()
# TODO 修复debug -> 更新python扩展解决