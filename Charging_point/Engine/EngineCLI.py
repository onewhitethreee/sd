"""
CLI para el módulo Engine del Charging Point.
Permite simular las acciones físicas del usuario en el CP (enchufar/desenchufar vehículo, simular averías).
"""

import threading
import sys
import os
import time
import uuid

# Añadir el directorio raíz al path para imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Message.MessageTypes import MessageTypes, ResponseStatus, MessageFields
from Common.Queue.KafkaManager import KafkaTopics
from Common.Config.ConsolePrinter import get_printer


class EngineCLI:
    def __init__(self, engine, logger):
        """
        Inicializa el CLI del Engine.

        Args:
            engine: Instancia de EV_CP_E
            logger: Logger para mostrar mensajes
        """
        self.engine = engine
        self.logger = logger
        self.running = False
        self.cli_thread = None
        self.printer = get_printer()

    def start(self):
        """Inicia el CLI en un hilo separado"""
        if self.cli_thread and self.cli_thread.is_alive():
            self.logger.warning("CLI already running")
            return

        self.running = True
        self.cli_thread = threading.Thread(
            target=self._run_cli, daemon=True, name="EngineCLI"
        )
        self.cli_thread.start()
        self.logger.debug("Engine CLI started")

    def stop(self):
        """Detiene el CLI"""
        self.running = False
        if self.cli_thread:
            self.logger.debug("Engine CLI stopped")

    def _show_menu(self):
        """Muestra el menú del CLI"""
        # 构建状态信息
        status_info = []
        status_info.append(f"CP ID: {self.engine.cp_id if self.engine.cp_id else 'Not initialized'}")

        status = self.engine.get_current_status()
        status_text = f"Status: {status}"
        if self.engine._manual_faulty_mode:
            status_text += " ⚠️  [MANUAL FAULTY MODE ACTIVE]"
        if self.engine.cp_service_stopped:
            status_text += " 🚫 [CP SERVICE STOPPED]"
        status_info.append(status_text)
        status_info.append(f"Charging: {'YES' if self.engine.is_charging else 'NO'}")

        if self.engine.is_charging and self.engine.current_session:
            status_info.append(f"Session ID: {self.engine.current_session['session_id']}")
            status_info.append(f"Driver ID: {self.engine.current_session['driver_id']}")
            status_info.append(f"Energy: {self.engine.current_session['energy_consumed_kwh']:.3f} kWh")
            status_info.append(f"Cost: €{self.engine.current_session['total_cost']:.2f}")

        # Mostrar sesión suspendida si existe
        if self.engine._suspended_session:
            status_info.append(f"⏸️  Suspended: {self.engine._suspended_session['session_id']} ({self.engine._suspended_session['energy_consumed_kwh']:.3f} kWh)")

        # 显示状态面板
        self.printer.print_panel("\n".join(status_info), title="Current Status", style="cyan")
        
        # 显示菜单
        menu_items = {
            "MANUAL CHARGING (from CP, sends request to Central)": [
                "[1] Request charging (manual charge_request to Central)",
                "[2] Stop charging (simulate vehicle unplug)"
            ],
            "ENGINE HARDWARE SIMULATION": [
                "[3] Simulate Engine failure",
                "[4] Simulate Engine recovery "
            ],
            "STATUS": [
                "[5] Show current status"
            ],
            "EXIT": [
                "[0] Exit menu (Engine continues running)"
            ]
        }
        self.printer.print_menu("EV_CP_E - ENGINE CONTROL MENU", menu_items)

    def _run_cli(self):
        """Ejecuta el loop principal del CLI"""
        self.logger.info("Engine CLI ready. Press ENTER to show menu...")

        while self.running and self.engine.running:
            try:
                # Esperar input del usuario
                user_input = input().strip()

                # Si el usuario presiona ENTER sin nada, mostrar menú
                if user_input == "":
                    self._show_menu()
                    continue

                # Procesar comandos
                if user_input == "1":
                    self._handle_vehicle_connected()
                elif user_input == "2":
                    self._handle_vehicle_disconnected()
                elif user_input == "3":
                    self._handle_simulate_failure()
                elif user_input == "4":
                    self._handle_simulate_recovery()
                elif user_input == "5":
                    self._show_status()
                elif user_input == "0":
                    self.printer.print_success("Exiting menu. Engine continues running in background.")
                    self.printer.print_info("(Press ENTER anytime to show menu again)")
                else:
                    self.printer.print_warning(f"Invalid option: '{user_input}'. Press ENTER to show menu.")

            except EOFError:
                # Si se cierra stdin, salir del CLI
                self.logger.debug("CLI input stream closed")
                break
            except Exception as e:
                self.logger.error(f"Error in CLI: {e}", exc_info=True)
                time.sleep(0.5)

    def _handle_vehicle_connected(self):
        """
        Simula que un vehículo se conecta físicamente al CP y solicita carga MANUALMENTE.

        Según PDF página 6:
        "Suministrar: proporcionar un servicio de recarga de dos formas:
         - Manualmente mediante una opción en el propio punto.
         - A través de una petición proviniente de la aplicación del conductor"

        Este método implementa la opción MANUAL: envía un charge_request a Central
        como lo haría un Driver, pero iniciado desde el propio CP.
        """
        if not self.engine.cp_id:
            self.printer.print_error("Cannot start charging: CP_ID not initialized yet")
            self.printer.print_info("Wait for Monitor to provide CP_ID")
            return
        if self.engine._manual_faulty_mode:
            self.printer.print_error("Cannot start charging: Engine in MANUAL FAULTY mode")
            self.printer.print_info("Simulate recovery first (option [4])")
            return
        if self.engine.cp_service_stopped:
            self.printer.print_error("Cannot start charging: CP service is STOPPED by administrator")
            self.printer.print_info("Charging point is out of service. Contact administrator or use 'resume' command from Central")
            return
        if self.engine.is_charging:
            self.printer.print_warning("Vehicle already connected and charging!")
            self.printer.print_key_value("Session ID", self.engine.current_session['session_id'])
            self.printer.print_key_value("Driver ID", self.engine.current_session['driver_id'])
            return

        # Solicitar Driver ID para la sesión manual
        self.printer.print_section("MANUAL CHARGING REQUEST", "-", 60)
        self.printer.print_info("(Sends charge_request to Central, like a Driver would)")

        driver_id = input("Enter Driver ID (or press ENTER for 'manual_driver'): ").strip()
        if not driver_id:
            driver_id = "manual_driver"

        self.printer.print_key_value("Driver ID", driver_id)
        self.printer.print_key_value("CP ID", self.engine.cp_id)
        self.printer.print_info("Sending charge_request to Central via Kafka...")

        # Enviar charge_request a Central (como lo haría un Driver)
        if (
            not self.engine.kafka_manager
            or not self.engine.kafka_manager.is_connected()
        ):
            self.printer.print_error("Kafka not connected - cannot send request to Central")
            return

        charge_request = {
            "type": "charge_request",
            "message_id": str(uuid.uuid4()),
            "cp_id": self.engine.cp_id,
            "driver_id": driver_id,
            "timestamp": int(time.time()),
        }

        success = self.engine.kafka_manager.produce_message(
            KafkaTopics.DRIVER_CHARGE_REQUESTS, charge_request
        )

        if success:
            self.printer.print_success("Charge request sent to Central successfully")
        else:
            self.printer.print_error("Failed to send charge request to Central")

    def _handle_vehicle_disconnected(self):
        """Maneja la simulación de desconexión del vehículo (desenchufar)"""
        if not self.engine.is_charging:
            self.printer.print_warning("No vehicle connected. Nothing to disconnect.")
            return

        self.printer.print_section("SIMULATING: Driver unplugs vehicle from CP", "-", 60)
        self.printer.print_info(f"Stopping charging session: {self.engine.current_session['session_id']}")

        # Detener la carga
        success = self.engine._stop_charging_session()

        if success:
            self.printer.print_success("Charging stopped successfully")
            self.printer.print_info("Final charging data sent to Central (via Kafka)")
        else:
            self.printer.print_error("Failed to stop charging")

    def _handle_simulate_failure(self):
        """Simula una avería del Engine (según PDF página 11)"""
        self.printer.print_section("SIMULATING: Engine hardware/software failure", "=", 60)
        self.printer.print_info("This will trigger Monitor to report FAULTY status to Central")

        # Activar modo de fallo manual - esto persiste hasta que se llame a recovery
        self.engine._manual_faulty_mode = True
        self.printer.print_success("Engine set to MANUAL FAULTY mode (persists until manual recovery)")

        # Enviar mensaje de fallo al Monitor
        if (
            self.engine.monitor_server
            and self.engine.monitor_server.has_active_clients()
        ):
            failure_message = {
                MessageFields.TYPE: MessageTypes.HEALTH_CHECK_RESPONSE,
                MessageFields.MESSAGE_ID: str(uuid.uuid4()),
                MessageFields.STATUS: ResponseStatus.SUCCESS,
                MessageFields.ENGINE_STATUS: "FAULTY",
                MessageFields.IS_CHARGING: self.engine.is_charging,
            }
            self.engine.monitor_server.send_broadcast_message(failure_message)
            self.printer.print_success("FAULTY signal sent to Monitor (via Socket)")

            # Si estamos cargando, SUSPENDER la carga (NO finalizar)
            if self.engine.is_charging:
                session_id = self.engine.current_session['session_id']
                driver_id = self.engine.current_session['driver_id']
                self.printer.print_warning(f"⚠️  Charging session '{session_id}' will be SUSPENDED")
                self.printer.print_info("Session data will be preserved and sent when Engine recovers")
                self.printer.print_info(f"Driver '{driver_id}' will be notified about the failure")
                self.engine._stop_charging_session()  # Llamará internamente a suspender
        else:
            self.printer.print_warning("No Monitor connected, cannot send FAULTY signal")

        self.printer.print_info("NOTE: Engine will remain in FAULTY mode until you use option [4]")
        self.printer.print_info("      to simulate recovery. Health checks will continue to report FAULTY.")
        if self.engine._suspended_session:
            self.printer.print_warning(f"      Session '{self.engine._suspended_session['session_id']}' is SUSPENDED and will be sent on recovery")

    def _handle_simulate_recovery(self):
        """Simula la recuperación del Engine de una avería"""
        self.printer.print_section("SIMULATING: Engine recovery from failure", "=", 60)
        self.printer.print_info("This will trigger Monitor to report ACTIVE status to Central")

        # Desactivar modo de fallo manual
        self.engine._manual_faulty_mode = False
        self.printer.print_success("Engine MANUAL FAULTY mode deactivated")

        # Si hay una sesión suspendida, procesarla antes de enviar el mensaje de recuperación
        if self.engine._suspended_session:
            self.printer.print_info(f"✓  Processing suspended session '{self.engine._suspended_session['session_id']}'...")
            self.engine._resume_suspended_session()

        # Enviar mensaje de recuperación al Monitor
        if (
            self.engine.monitor_server
            and self.engine.monitor_server.has_active_clients()
        ):
            recovery_message = {
                MessageFields.TYPE: MessageTypes.HEALTH_CHECK_RESPONSE,
                MessageFields.MESSAGE_ID: str(uuid.uuid4()),
                MessageFields.STATUS: ResponseStatus.SUCCESS,
                MessageFields.ENGINE_STATUS: "ACTIVE",
                MessageFields.IS_CHARGING: self.engine.is_charging,
            }
            self.engine.monitor_server.send_broadcast_message(recovery_message)
            self.printer.print_success("ACTIVE signal sent to Monitor (via Socket)")
            self.printer.print_success("Engine recovered! Health checks will now report ACTIVE status.")
        else:
            self.printer.print_warning("No Monitor connected, cannot send ACTIVE signal")

    def _show_status(self):
        """Muestra el estado actual del Engine"""
        # 构建状态信息
        status_details = []
        status_details.append(f"CP ID: {self.engine.cp_id if self.engine.cp_id else 'Not initialized'}")

        status = self.engine.get_current_status()
        status_details.append(f"Engine Status: {status}")
        if self.engine._manual_faulty_mode:
            status_details.append("⚠️  MANUAL FAULTY MODE: ACTIVE (use option [4] to recover)")
        if self.engine.cp_service_stopped:
            status_details.append("🚫 CP SERVICE STOPPED: Charging not allowed (admin must resume from Central)")

        status_details.append(f"Running: {self.engine.running}")
        status_details.append(f"Charging: {self.engine.is_charging}")

        if self.engine.monitor_server:
            status_details.append(f"Monitor Server: Running on {self.engine.engine_listen_address[0]}:{self.engine.engine_listen_address[1]}")
            status_details.append(f"Monitor Connected: {self.engine.monitor_server.has_active_clients()}")
        else:
            status_details.append("Monitor Server: Not initialized")

        if self.engine.is_charging and self.engine.current_session:
            session = self.engine.current_session
            duration = time.time() - session['start_time']
            energy = session['energy_consumed_kwh']
            cost = session['total_cost']
            price = session['price_per_kwh']

            status_details.append("\n🔋 CURRENT CHARGING SESSION:")
            status_details.append(f"  Session ID: {session['session_id']}")
            status_details.append(f"  Driver ID: {session['driver_id']}")
            status_details.append(f"  Duration: {duration:.1f}s")
            status_details.append(f"  Energy Consumed: {energy:.3f} kWh")
            status_details.append(f"  Total Cost: €{cost:.2f}")
            status_details.append(f"  Price: €{price}/kWh")



            # 显示实时进度（如果设置了最大充电时长）
            max_duration = self.engine.config.get_max_charging_duration()
            if max_duration > 0:
                progress = min(100, (duration / max_duration) * 100)
                status_details.append(f"  Progress: {progress:.1f}% ({duration:.0f}s / {max_duration}s)")

        # Mostrar información de sesión suspendida si existe
        if self.engine._suspended_session:
            session = self.engine._suspended_session
            status_details.append("\n⏸️  SUSPENDED SESSION (waiting for recovery):")
            status_details.append(f"  Session ID: {session['session_id']}")
            status_details.append(f"  Driver ID: {session['driver_id']}")
            status_details.append(f"  Energy Consumed: {session['energy_consumed_kwh']:.3f} kWh")
            status_details.append(f"  Total Cost: €{session['total_cost']:.2f}")
            status_details.append(f"  Duration: {session['duration']:.1f}s")
            status_details.append("  ⚠️  Will be sent to Central and Driver when Engine recovers")

        self.printer.print_panel("\n".join(status_details), title="CURRENT ENGINE STATUS", style="blue")
