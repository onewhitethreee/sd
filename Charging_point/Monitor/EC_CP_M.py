"""
Módulo que monitoriza la salud de todo el punto de recarga y que reporta a la CENTRAL cualquier avería de este. Sirve igualmente para autenticar y registrar a los CP en la central cuando sea oportuno.
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager


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
                id_cp = self.config.get_client_id()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

    def _accept_engine_connection(self):
        """
        接受来自EV_CP_E的连接
        """
        pass

    def _connect_to_central(self):
        """
        连接到EV_Central
        """
        pass
    def _handle_disconnection(self):
        """
        处理断开连接和重试机制
        """
        pass

    def _register_with_central(self):
        """
        和central注册一个charging point
        """
        pass
    def _send_heartbeat(self):
        """
        发送心跳消息以保持与中央的连接
        """
        pass
    def autheticate_charging_point(self):
        """
        认证充电点
        """
        pass
    def _authenticate_with_central(self):
        """
        向central认证
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
        pass
    
    def start(self):
        self.logger.info(f"Starting EV_CP_M module")
        self.logger.info(
            f"Listening  to EV_CP_E at {self.args.ip_port_ev_cp_e[0]}:{self.args.ip_port_ev_cp_e[1]}"
        )
        self.logger.info(
            f"Connecting to EV_Central at {self.args.ip_port_ev_central[0]}:{self.args.ip_port_ev_central[1]}"
        )
        self.logger.info(f"Point ID: {self.args.id_cp}")

        # Aquí iría la lógica para iniciar el módulo, conectar al broker, leer sensores, etc.
        try:
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            self.logger.info("Shutting down EV CP M")
            sys.exit(0)


if __name__ == "__main__":
    logger = CustomLogger.get_logger()

    ev_cp_m = EV_CP_M(logger=logger)
    ev_cp_m.start()
