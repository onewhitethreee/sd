"""
Aplicación que usan los consumidores para usar los puntos de recarga
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager
class Driver:
    def __init__(self, debug_mode=False, logger=None):
        self.debug_mode = debug_mode
        self.logger = logger
        if not self.debug_mode:

            self.tools = AppArgumentParser("Driver", "Módulo de control del punto de recarga")            
            self.tools.add_argument("broker", type=ip_port_type, help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)")
            self.tools.add_argument("id_client", type=str, help="Identificador único del cliente")
            self.args = self.tools.parse_args()
        else:
            class Args:
                broker = ("localhost", 9092)
                id_client = "client_001"
            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")
    
    def start(self):
        self.logger.info(f"Starting Driver module")
        self.logger.info(f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}")
        self.logger.info(f"Client ID: {self.args.id_client}")
        # Aquí iría la lógica para iniciar el módulo, conectar al broker, leer sensores, etc.
        try:
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            self.logger.info("Shutting down EV Central")
            sys.exit(0)
if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    config = ConfigManager()
    debug_mode = config.get_debug_mode()
    driver = Driver(debug_mode=debug_mode, logger=logger)
    driver.start()
