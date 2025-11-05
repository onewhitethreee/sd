
import threading
from typing import TYPE_CHECKING
import time

if TYPE_CHECKING:
    from Driver.EV_Driver import Driver


class DriverCLI:
    """
    CLI para driver
    """

    def __init__(self, driver: "Driver"):
        """
        Inicializa el DriverCLI

        Args:
            driver: Instancia del Driver
        """
        self.driver = driver
        self.running = False
        self.cli_thread = None
        self.logger = driver.logger

    def start(self):
        """
        Inicia el CLI interactivo en un hilo separado
        """
        if self.running:
            self.logger.warning("Driver CLI ya está en ejecución")
            return

        self.running = True
        self.cli_thread = threading.Thread(target=self._run_cli, daemon=True)
        self.cli_thread.start()
        self.logger.info("Driver CLI iniciado")

    def stop(self):
        """Detiene el CLI interactivo"""
        if not self.running:
            return

        self.running = False
        if self.cli_thread:
            self.cli_thread.join(timeout=2)
        self.logger.info("Driver CLI detenido")

    def _run_cli(self):
        """
        Ejecuta el loop principal del CLI
        """
        self.logger.info("Driver CLI ready. Press ENTER to show menu...")

        while self.running and self.driver.running:
            try:
                user_input = input().strip()

                if not user_input:
                    self._show_menu()
                    continue

                self._process_command(user_input)

            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            except Exception as e:
                self.logger.error(f"Error: {e}")

    def _show_menu(self):
        """
        Muestra el menú
        """
        print("\n" + "=" * 60)
        print("  EV_DRIVER - DRIVER CONTROL MENU")
        print("=" * 60)
        print(f"  Driver ID: {self.driver.args.id_client}")

        # 显示当前充电状态
        with self.driver.lock:
            if self.driver.current_charging_session:
                session = self.driver.current_charging_session
                print(f"  Status: CHARGING")
                print(f"  Session ID: {session.get('session_id', 'N/A')}")
                print(f"  CP ID: {session.get('cp_id', 'N/A')}")
                print(f"  Energy: {session.get('energy_consumed_kwh', 0.0):.3f} kWh")
                print(f"  Cost: €{session.get('total_cost', 0.0):.2f}")
            else:
                print(f"  Status: IDLE")

        print("-" * 60)
        print("  CHARGING OPERATIONS:")
        print("  [1] List available charging points")
        print("  [2] Request charging (requires CP ID)")
        print("  [3] Stop current charging session")
        print()
        print("  INFORMATION:")
        print("  [4] Show current charging status")
        print("  [5] Show charging history")
        print()
        print("  [0] Exit Driver Application")
        print("=" * 60)

    def _process_command(self, command: str):
        """
        处理用户输入的命令

        Args:
            command: 用户输入的命令字符串（数字选项）
        """
        try:
            if command == "0":
                self.driver.running = False
                self.running = False

            elif command == "1":
                self._handle_list_command()

            elif command == "2":
                cp_id = input("Introduce el ID del punto de carga: ").strip()
                if cp_id:
                    self._handle_charge_command(cp_id)
                else:
                    print("Error: El ID del punto de carga no puede estar vacío")

            elif command == "3":
                self._handle_stop_command()

            elif command == "4":
                self._handle_status_command()

            elif command == "5":
                self._handle_history_command()

            else:
                print("Por favor, introduce un número válido del menú.")

        except Exception as e:
            self.logger.error(f"Error al procesar el comando: {e}")

    def _handle_list_command(self):
        """
        Muestra la lista de puntos de carga disponibles
        """
        try:
            self.driver._request_available_cps()
            with self.driver.lock:
                if self.driver.available_charging_points:
                    print(f"\nLista de puntos de carga disponibles:")
                    print("-" * 80)
                    self.driver._formatter_charging_points(
                        self.driver.available_charging_points
                    )
                else:
                    print("No hay puntos de carga disponibles actualmente.")

        except Exception as e:
            self.logger.error(f"Error al obtener la lista de puntos de carga: {e}")

    def _handle_charge_command(self, cp_id: str):
        """
        Muestra la información del punto de carga seleccionado y envía la solicitud de carga
        """
        try:
            with self.driver.lock:
                if self.driver.current_charging_session:
                    session = self.driver.current_charging_session
                    print(f"Error: Ya hay una sesión de carga activa")
                    print(f"  ID de sesión: {session.get('session_id')}")
                    print(f"  Punto de carga: {session.get('cp_id')}")
                    return

            with self.driver.lock:
                available_ids = [
                    cp.get("id") for cp in self.driver.available_charging_points
                ]
                if cp_id not in available_ids:
                    print(f"Advertencia: El punto de carga {cp_id} puede no estar en la lista de disponibles")
                    return

            # Enviar solicitud de carga
            print(f"Enviando solicitud de carga al punto de carga {cp_id}...")
            success = self.driver._send_charge_request(cp_id)

            if success:
                print(f"✓ Solicitud de carga enviada")
                print("Esperando respuesta del sistema Central...")
            else:
                print(f"✗ Solicitud de carga fallida")

        except Exception as e:
            self.logger.error(f"Error al enviar solicitud de carga: {e}")

    def _handle_stop_command(self):
        """
        Maneja el comando de detener la carga
        """
        try:
            with self.driver.lock:
                if not self.driver.current_charging_session:
                    print("No hay ninguna sesión de carga activa")
                    return

                session = self.driver.current_charging_session
                print(f"Deteniendo sesión de carga...")
                print(f"  ID de sesión: {session.get('session_id')}")
                print(f"  ID de punto de carga: {session.get('cp_id')}")

            # Enviar solicitud de detener carga
            success = self.driver._send_stop_charging_request()

            if success:
                print(f"✓ Solicitud de detener carga enviada")
                print("Esperando que la sesión de carga finalice...")
            else:
                print(f"✗ Solicitud de detener carga fallida")

        except Exception as e:
            self.logger.error(f"Error al detener carga: {e}")

    def _handle_status_command(self):
        """Maneja el comando de estado - Muestra el estado actual de carga"""
        try:
            with self.driver.lock:
                if not self.driver.current_charging_session:
                    print("\nEstado de carga actual: Libre")
                    print("No hay ninguna sesión de carga activa.")
                    return

                session = self.driver.current_charging_session

                print("\nEstado de carga actual:")
                print("=" * 60)
                print(f"  ID de sesión:         {session.get('session_id', 'N/A')}")
                print(f"  ID de punto de carga:       {session.get('cp_id', 'N/A')}")
                print(f"  Estado:           Charging")
                print(
                    f"  Energía consumida:     {session.get('energy_consumed_kwh', 0.0):.3f} kWh"
                )
                print(f"  Costo total:       {session.get('total_cost', 0.0):.2f} €")

                # Calcular duración de carga (si hay tiempo de inicio)
                if "start_time" in session:

                    elapsed = time.time() - session.get("start_time", time.time())
                    minutes = int(elapsed // 60)
                    seconds = int(elapsed % 60)
                    print(f"  Duración de carga:       {minutes} min {seconds} seg")

                print("=" * 60)

        except Exception as e:
            self.logger.error(f"Error al obtener estado de carga: {e}")

    def _handle_history_command(self):
        """
        Maneja el comando de historial - Consulta y muestra el historial de carga
        """
        try:
            print("\nConsultando historial de carga...")

            self.driver._request_charging_history()

            # Nota: La respuesta llegará de forma asíncrona y será manejada por DriverMessageDispatcher._handle_charging_history_response

        except Exception as e:
            print(f"\n❌ Error al consultar historial de carga: {e}")
