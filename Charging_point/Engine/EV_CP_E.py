"""
Módulo que recibe la información de los sensores y se conecta al sistema monitor
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.ConfigManager import ConfigManager
from Common.CustomLogger import CustomLogger
from Common.MySockerServer import MySocketServer


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
                help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)",
            )
            self.tools.add_argument(
                "ip_port_ev_m",
                type=ip_port_type,
                help="IP y puerto del EV_M (formato IP:PORT)",
            )
            self.args = self.tools.parse_args()
        else:

            class Args:
                broker = self.config.get_broker()
                ip_port_ev_m = self.config.get_ip_port_ev_m()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")
        self.running = False
        self.is_charging = False

    def _init_connections(self):  # TODO kafka client implementation
        """
        去和monitor和ev_m建立连接
        """
        try:
            self.socket_server = MySocketServer(
                host=self.args.ip_port_ev_m[0],
                port=self.args.ip_port_ev_m[1],
                logger=self.logger,
                message_handler=self._process_monitor_message,
            )
            self.socket_server.start()
            self.running = True
            self.logger.info(f"Engine started and listening on {self.args.ip_port_ev_m[0]}:{self.args.ip_port_ev_m[1]}")
        except Exception as e:
            self.logger.error(f"Error initializing connections: {e}")
            sys.exit(1)

    def _shutdown_system(self):
        """
        关闭系统连接
        """
        self.running = False
        if self.is_charging:
            self._stop_charging_session(ev_id=None)  # 停止当前充电会话
            self.is_charging = False
            self.logger.info("Charging session stopped.")
        if hasattr(self, 'socket_server'):
            self.socket_server.stop()
            self.logger.info("Socket server stopped.")
        self.logger.info("System shutdown complete.")
        sys.exit(0)

    def _process_monitor_message(self, message):
        """
        处理来自monitor的消息
        """
        msg_type = message.get("type")
        self.logger.debug(f"Received message of type: {msg_type}")


    def _manage_charging_session(self, session_data):
        """
        管理充电会话
        """
        pass

    def _start_charging_session(self, ev_id):
        """
        启动充电会话
        """
        pass

    def _stop_charging_session(self, ev_id):
        """
        停止充电会话
        """
        pass

    def _update_status(self, status):
        """
        更新充电点状态
        """
        pass

    def initialize_system(self):
        self.logger.info("Initializing EV_CP_E module")
        self._init_connections()

    def start(self):
        self.logger.info(f"Starting EV_CP_E module")
        self.logger.info(
            f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )
        self.logger.info(
            f"Connecting to EV_M at {self.args.ip_port_ev_m[0]}:{self.args.ip_port_ev_m[1]}"
        )
        # Aquí iría la lógica para iniciar el módulo, conectar al broker, leer sensores, etc.
        try:
            while self.running:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            self.logger.info("Shutting down EV CP E")
            sys.exit(0)


if __name__ == "__main__":
    logger = CustomLogger.get_logger()

    ev_cp_e = EV_CP_E(logger=logger)
    ev_cp_e.start()
