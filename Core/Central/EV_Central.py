"""
Módulo que representa la central de control de toda la solución. Implementa la lógica y gobierno de todo el sistema.
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type


class EV_Central:
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        if not self.debug_mode:
            self.tools = AppArgumentParser(
                "EV_Central",
                "Sistema Central de Control para Puntos de Recarga de Vehículos Eléctricos",
            )
            self.tools.add_argument("listen_port", type=int, help="Puerto de escuha")
            self.tools.add_argument(
                "broker",
                type=ip_port_type,
                help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)",
            )
            self.tools.add_argument(
                "--db",
                type=ip_port_type,
                help="IP y puerto del servidor de base de datos (formato IP:PORT)",
                default=("localhost", 5432),
            )
            self.args = self.tools.parse_args()
        else:

            class Args:
                listen_port = 5000
                broker = ("localhost", 9092)
                db = ("localhost", 5432)

            self.args = Args()

    def start(self):
        print(f"Starting EV Central on port {self.args.listen_port}")
        print(f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}")
        print(f"Connecting to Database at {self.args.db[0]}:{self.args.db[1]}")
        # Aquí iría la lógica para iniciar la central, escuchar en el puerto, conectar a la base de datos, etc.
        try:
            while True:
                pass  # Simulación de la ejecución continua del servicio
        except KeyboardInterrupt:
            print("Shutting down EV Central")
            sys.exit(0)


if __name__ == "__main__":
    ev_central = EV_Central(debug_mode=True)
    ev_central.start()
