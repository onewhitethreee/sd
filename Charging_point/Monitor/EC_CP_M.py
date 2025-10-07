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
        self.engine_server = None  # Servidor para aceptar conexiones de EV_CP_E
        self.running = False
        self.RETRY_INTERVAL = 5  # Intervalo de reintento en segundos

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

    def _start_heartbeat_thread(self):
        """
        启动发送心跳的线程
        """
        heartbeat_thread = threading.Thread(target=self._send_heartbeat, daemon=True)
        heartbeat_thread.start()

    def autheticate_charging_point(self):
        """
        认证充电点
        """
        pass

    def _check_engine_health(self):
        """
        检查EV_CP_E的健康状态
        """
        pass

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

        elif message_type == 'SERVER_SHUTDOWN':
            self.logger.warning("Central server is shutting down")
            self._handle_server_shutdown()
        
        elif message_type == 'CONNECTION_ERROR':
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

        # Desconectar clientes
        if self.central_client:
            self.central_client.disconnect()

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
            self.logger.info(f"Connection retry {retry_count}/{max_retries}")

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
                threading.Thread(target=self._retry_registration, daemon=True).start()
        else:
            self.logger.error("Failed to connect to EV_Central")
            threading.Thread(target=self._ensure_connection_and_registration, daemon=True).start()

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


if __name__ == "__main__":
    logger = CustomLogger.get_logger()

    ev_cp_m = EV_CP_M(logger=logger)
    ev_cp_m.start()
