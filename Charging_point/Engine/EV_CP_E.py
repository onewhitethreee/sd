"""
Módulo que recibe la información de los sensores y se conecta al sistema central
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
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

            self.tools = AppArgumentParser("EV_CP_E", "Módulo de gestión de sensores y comunicación con la central")            
            self.tools.add_argument("broker", type=ip_port_type, help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)")
            self.tools.add_argument("ip_port_ev_m", type=ip_port_type, help="IP y puerto del EV_M (formato IP:PORT)")
            self.args = self.tools.parse_args()
        else:
            class Args:
                broker = self.config.get_broker()
                ip_port_ev_m = self.config.get_ip_port_ev_m()
            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        



    def _init_connections(self): # TODO kafka client implementation
        """
        去和central和ev_m建立连接
        """
        self._connect_to_central()

    def _shutdown_system(self):
        """
        关闭系统连接
        """
        pass

    def _process_central_message(self, message):
        """
        处理来自central的消息
        """
        pass

    def send_register_to_central(self):
        """
        向central注册 charging point
        """
        pass
    def send_charging_data_to_central(self, data):
        """
        向central发送充电数据
        """
        pass
    def send_charging_complete_to_central(self, data):
        """
        向central发送充电完成数据
        """
        pass
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
        self.logger.info(f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}")
        self.logger.info(f"Connecting to EV_M at {self.args.ip_port_ev_m[0]}:{self.args.ip_port_ev_m[1]}")
        # Aquí iría la lógica para iniciar el módulo, conectar al broker, leer sensores, etc.
        try:
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            self.logger.info("Shutting down EV CP E")
            sys.exit(0)


if __name__ == "__main__":
    logger = CustomLogger.get_logger()

    ev_cp_e = EV_CP_E(logger=logger)
    ev_cp_e.start()
