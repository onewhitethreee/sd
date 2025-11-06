import threading
from typing import TYPE_CHECKING
import time
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Config.ConsolePrinter import get_printer

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
        self.printer = get_printer()

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
        # 获取当前状态信息
        status_info = []
        with self.driver.lock:
            status_info.append(f"Driver ID: {self.driver.args.id_client}")
            if self.driver.current_charging_session:
                session = self.driver.current_charging_session
                status_info.append(f"Status: CHARGING")
                status_info.append(f"Session ID: {session.get('session_id', 'N/A')}")
                status_info.append(f"CP ID: {session.get('cp_id', 'N/A')}")
                status_info.append(f"Energy: {session.get('energy_consumed_kwh', 0.0):.3f} kWh")
                status_info.append(f"Cost: €{session.get('total_cost', 0.0):.2f}")
            else:
                status_info.append("Status: IDLE")
        
        # 显示状态面板
        self.printer.print_panel("\n".join(status_info), title="Current Status", style="cyan")
        
        # 显示菜单
        menu_items = {
            "CHARGING OPERATIONS": [
                "[1] List available charging points",
                "[2] Request charging (requires CP ID)",
                "[3] Stop current charging session"
            ],
            "INFORMATION": [
                "[4] Show current charging status",
                "[5] Show charging history"
            ],
            "EXIT": [
                "[0] Exit Driver Application"
            ]
        }
        self.printer.print_menu("EV_DRIVER - DRIVER CONTROL MENU", menu_items)

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
                cp_id = input("Enter Charging Point ID: ").strip()
                if cp_id:
                    self._handle_charge_command(cp_id)
                else:
                    self.printer.print_error("Charging Point ID cannot be empty")

            elif command == "3":
                self._handle_stop_command()

            elif command == "4":
                self._handle_status_command()

            elif command == "5":
                self._handle_history_command()

            else:
                self.printer.print_warning("Please enter a valid menu option number.")

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
                    # 准备表格数据
                    headers = ["#", "CP ID", "Location", "Price (€/kWh)", "Status"]
                    rows = []
                    for i, cp in enumerate(self.driver.available_charging_points, 1):
                        rows.append([
                            str(i),
                            cp.get("id", "N/A"),
                            cp.get("location", "N/A"),
                            f"€{cp.get('price_per_kwh', 0.0):.4f}",
                            cp.get("status", "N/A")
                        ])
                    self.printer.print_table("Available Charging Points", headers, rows)
                else:
                    self.printer.print_warning("No charging points available currently.")

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
                    error_info = f"Session ID: {session.get('session_id')}\nCP ID: {session.get('cp_id')}"
                    self.printer.print_error("A charging session is already active")
                    self.printer.print_info(error_info)
                    return

            with self.driver.lock:
                available_ids = [
                    cp.get("id") for cp in self.driver.available_charging_points
                ]
                if cp_id not in available_ids:
                    self.printer.print_warning(f"Charging point {cp_id} may not be in the available list")
                    return

            # Enviar solicitud de carga
            self.printer.print_info(f"Sending charging request to charging point {cp_id}...")
            success = self.driver._send_charge_request(cp_id)

            if success:
                self.printer.print_success("Charging request sent")
                self.printer.print_info("Waiting for response from Central system...")
            else:
                self.printer.print_error("Charging request failed")

        except Exception as e:
            self.logger.error(f"Error al enviar solicitud de carga: {e}")

    def _handle_stop_command(self):
        """
        Maneja el comando de detener la carga
        """
        try:
            with self.driver.lock:
                if not self.driver.current_charging_session:
                    self.printer.print_warning("No active charging session")
                    return

                session = self.driver.current_charging_session
                self.printer.print_info("Stopping charging session...")
                self.printer.print_key_value("Session ID", session.get('session_id', 'N/A'))
                self.printer.print_key_value("CP ID", session.get('cp_id', 'N/A'))

            # Enviar solicitud de detener carga
            success = self.driver._send_stop_charging_request()

            if success:
                self.printer.print_success("Stop charging request sent")
                self.printer.print_info("Waiting for charging session to complete...")
            else:
                self.printer.print_error("Stop charging request failed")

        except Exception as e:
            self.logger.error(f"Error al detener carga: {e}")

    def _handle_status_command(self):
        """Maneja el comando de estado - Muestra el estado actual de carga"""
        try:
            with self.driver.lock:
                if not self.driver.current_charging_session:
                    self.printer.print_info("Current charging status: IDLE")
                    self.printer.print_warning("No active charging session")
                    return

                session = self.driver.current_charging_session

                # 构建详细信息面板
                details = []
                details.append(f"Session ID:      {session.get('session_id', 'N/A')}")
                details.append(f"CP ID:           {session.get('cp_id', 'N/A')}")
                details.append(f"Status:          Charging")
                details.append(f"Energy Consumed: {session.get('energy_consumed_kwh', 0.0):.3f} kWh")
                details.append(f"Total Cost:      €{session.get('total_cost', 0.0):.2f}")

                # Calcular duración de carga (si hay tiempo de inicio)
                if "start_time" in session:
                    elapsed = time.time() - session.get("start_time", time.time())
                    minutes = int(elapsed // 60)
                    seconds = int(elapsed % 60)
                    details.append(f"Duration:        {minutes} min {seconds} seg")

                self.printer.print_panel("\n".join(details), title="Current Charging Status", style="green")

        except Exception as e:
            self.logger.error(f"Error al obtener estado de carga: {e}")

    def _handle_history_command(self):
        """
        Maneja el comando de historial - Consulta y muestra el historial de carga
        """
        try:
            self.printer.print_info("Requesting charging history...")

            self.driver._request_charging_history()

            # Nota: La respuesta llegará de forma asíncrona y será manejada por DriverMessageDispatcher._handle_charging_history_response

        except Exception as e:
            self.printer.print_error(f"Failed to request charging history: {e}")
