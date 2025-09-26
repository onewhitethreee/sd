"""
Módulo que monitoriza la salud de todo el punto de recarga y que reporta a la CENTRAL cualquier avería de este. Sirve igualmente para autenticar y registrar a los CP en la central cuando sea oportuno.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager
class EV_CP_M:
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        if not self.debug_mode:
            self.tools = AppArgumentParser("EV_CP_M", "Módulo de monitorización del punto de recarga")
            self.tools.add_argument("ip_port_ev_cp_e", type=ip_port_type, help="IP y puerto del EV_CP_E (formato IP:PORT)")
            self.tools.add_argument("ip_port_ev_central", type=ip_port_type, help="IP y puerto del EV_CP_Central (formato IP:PORT)")
            self.tools.add_argument("id_cp", type=str, help="Identificador único del punto de recarga")
            self.args = self.tools.parse_args()
        else:
            class Args:
                ip_port_ev_cp_e = ("localhost", 6000)
                ip_port_ev_central = ("localhost", 5000)
                id_cp = "cp_001"
            self.args = Args()
            logger.debug("Debug mode is ON. Using default arguments.")
    
    def start(self):
        logger.info(f"Starting EV_CP_M module")
        logger.info(f"Connecting to EV_CP_E at {self.args.ip_port_ev_cp_e[0]}:{self.args.ip_port_ev_cp_e[1]}")
        logger.info(f"Connecting to EV_Central at {self.args.ip_port_ev_central[0]}:{self.args.ip_port_ev_central[1]}")
        logger.info(f"Point ID: {self.args.id_cp}")

        # Aquí iría la lógica para iniciar el módulo, conectar al broker, leer sensores, etc.
        try:
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            logger.info("Shutting down EV CP M")
            sys.exit(0)
if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    config = ConfigManager()
    debug_mode = config.get_debug_mode()

    ev_cp_m = EV_CP_M(debug_mode=debug_mode)
    ev_cp_m.start()
