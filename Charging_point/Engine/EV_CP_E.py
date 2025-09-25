"""
Módulo que recibe la información de los sensores y se conecta al sistema central
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.CustomLogger import CustomLogger

class EV_CP_E:
    def __init__(self, debug_mode=False):
        if not debug_mode:

            self.tools = AppArgumentParser("EV_CP_E", "Módulo de gestión de sensores y comunicación con la central")            
            self.tools.add_argument("broker", type=ip_port_type, help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)")
            self.tools.add_argument("ip_port_ev_m", type=ip_port_type, help="IP y puerto del EV_M (formato IP:PORT)")
            self.args = self.tools.parse_args()
        else:
            class Args:
                broker = ("localhost", 9092)
                ip_port_ev_m = ("localhost", 6000)
            self.args = Args()
        
    def start(self):
        logger.info(f"Starting EV_CP_E module")
        logger.info(f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}")
        logger.info(f"Connecting to EV_M at {self.args.ip_port_ev_m[0]}:{self.args.ip_port_ev_m[1]}")
        # Aquí iría la lógica para iniciar el módulo, conectar al broker, leer sensores, etc.
        try:
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            logger.info("Shutting down EV CP E")
            sys.exit(0)
if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    ev_cp_e = EV_CP_E(debug_mode=True)
    ev_cp_e.start()
