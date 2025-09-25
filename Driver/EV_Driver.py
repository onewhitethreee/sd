"""
Aplicación que usan los consumidores para usar los puntos de recarga
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type

class Driver:
    def __init__(self, debug_mode=False):
        if not debug_mode:

            self.tools = AppArgumentParser("Driver", "Módulo de control del punto de recarga")            
            self.tools.add_argument("broker", type=ip_port_type, help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)")
            self.tools.add_argument("id_client", type=str, help="Identificador único del cliente")
            self.args = self.tools.parse_args()
        else:
            class Args:
                broker = ("localhost", 9092)
                id_client = "client_001"
            self.args = Args()
    
    def start(self):
        print(f"Starting Driver module")
        print(f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}")
        print(f"Client ID: {self.args.id_client}")
        # Aquí iría la lógica para iniciar el módulo, conectar al broker, leer sensores, etc.
        try:
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            print("Shutting down EV Central")
            sys.exit(0)
if __name__ == "__main__":
    driver = Driver(debug_mode=True)
    driver.start()
