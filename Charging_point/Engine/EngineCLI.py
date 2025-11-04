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

    def start(self):
        """Inicia el CLI en un hilo separado"""
        if self.cli_thread and self.cli_thread.is_alive():
            self.logger.warning("CLI already running")
            return

        self.running = True
        self.cli_thread = threading.Thread(
            target=self._run_cli,
            daemon=True,
            name="EngineCLI"
        )
        self.cli_thread.start()
        self.logger.info("Engine CLI started")

    def stop(self):
        """Detiene el CLI"""
        self.running = False
        if self.cli_thread:
            self.logger.info("Engine CLI stopped")

    def _show_menu(self):
        """Muestra el menú del CLI"""
        print("\n" + "=" * 60)
        print("  EV_CP_E - ENGINE CONTROL MENU")
        print("=" * 60)
        print(f"  CP ID: {self.engine.cp_id if self.engine.cp_id else 'Not initialized'}")

        status = self.engine.get_current_status()
        status_indicator = f"  Status: {status}"
        if self.engine._manual_faulty_mode:
            status_indicator += " ⚠️  [MANUAL FAULTY MODE ACTIVE]"
        print(status_indicator)

        print(f"  Charging: {'YES' if self.engine.is_charging else 'NO'}")

        if self.engine.is_charging and self.engine.current_session:
            print(f"  Session ID: {self.engine.current_session['session_id']}")
            print(f"  Driver ID: {self.engine.current_session['driver_id']}")
            print(f"  Energy: {self.engine.current_session['energy_consumed_kwh']:.3f} kWh")
            print(f"  Cost: €{self.engine.current_session['total_cost']:.2f}")

        print("-" * 60)
        print("  MANUAL CHARGING (from CP, sends request to Central):")
        print("  [1] Request charging (manual charge_request to Central)")
        print("  [2] Stop charging (simulate vehicle unplug)")
        print()
        print("  ENGINE HARDWARE SIMULATION:")
        print("  [3] Simulate Engine failure (Send KO to Monitor)")
        print("  [4] Simulate Engine recovery (Send OK to Monitor)")
        print()
        print("  STATUS:")
        print("  [5] Show current status")
        print()
        print("  [0] Exit menu (Engine continues running)")
        print("=" * 60)
        print()
        print("  NOTE: Option [1] simulates manual charging from the CP itself")
        print("        (as specified in PDF page 6). Central will handle the")
        print("        session creation and use the CP's configured price.")

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
                    print("\n✓ Exiting menu. Engine continues running in background.")
                    print("  (Press ENTER anytime to show menu again)\n")
                else:
                    print(f"\n⚠ Invalid option: '{user_input}'. Press ENTER to show menu.\n")

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
        print("\n" + "-" * 60)

        if not self.engine.cp_id:
            print("❌ Cannot start charging: CP_ID not initialized yet")
            print("   Wait for Monitor to provide CP_ID")
            print("-" * 60)
            return
        if self.engine._manual_faulty_mode:
            print("❌ Cannot start charging: Engine in MANUAL FAULTY mode")
            print("   Simulate recovery first (option [4])")
            print("-" * 60)
            return
        if self.engine.is_charging:
            print("⚠ Vehicle already connected and charging!")
            print(f"   Session ID: {self.engine.current_session['session_id']}")
            print(f"   Driver ID: {self.engine.current_session['driver_id']}")
            print("-" * 60)
            return

        # Solicitar Driver ID para la sesión manual
        print("🔌 MANUAL CHARGING REQUEST")
        print("   (Sends charge_request to Central, like a Driver would)")
        print()

        driver_id = input("   Enter Driver ID (or press ENTER for 'manual_driver'): ").strip()
        if not driver_id:
            driver_id = "manual_driver"

        print()
        print(f"   Driver ID: {driver_id}")
        print(f"   CP ID: {self.engine.cp_id}")
        print()
        print("   Sending charge_request to Central via Kafka...")

        # Enviar charge_request a Central (como lo haría un Driver)
        if not self.engine.kafka_manager or not self.engine.kafka_manager.is_connected():
            print("❌ Kafka not connected - cannot send request to Central")
            print("-" * 60)
            return

        charge_request = {
            "type": "charge_request",
            "message_id": str(uuid.uuid4()),
            "cp_id": self.engine.cp_id,
            "driver_id": driver_id,
            "timestamp": int(time.time()),
        }

        success = self.engine.kafka_manager.produce_message(
            KafkaTopics.DRIVER_CHARGE_REQUESTS,
            charge_request
        )

        if success:
            print("✓ Charge request sent to Central successfully")
            print()
            print("   Central will:")
            print("   1. Validate this CP is available")
            print("   2. Create charging session in database")
            print("   3. Get price from CP configuration")
            print("   4. Send start_charging_command to this Engine")
            print("   5. Engine will start charging automatically")
            print()
            print("   Wait for Central's response...")
        else:
            print("❌ Failed to send charge request to Kafka")

        print("-" * 60)

    def _handle_vehicle_disconnected(self):
        """Maneja la simulación de desconexión del vehículo (desenchufar)"""
        print("\n" + "-" * 60)

        if not self.engine.is_charging:
            print("⚠ No vehicle connected. Nothing to disconnect.")
            print("-" * 60)
            return

        print("🔌 SIMULATING: Driver unplugs vehicle from CP")
        print(f"   Stopping charging session: {self.engine.current_session['session_id']}")

        # Detener la carga
        success = self.engine._stop_charging_session()

        if success:
            print("✓ Charging stopped successfully")
            print("   Final charging data sent to Central (via Kafka)")
        else:
            print("❌ Failed to stop charging")

        print("-" * 60)

    def _handle_simulate_failure(self):
        """Simula una avería del Engine (según PDF página 11)"""
        print("\n" + "-" * 60)
        print("💥 SIMULATING: Engine hardware/software failure")
        print("   This will trigger Monitor to report FAULTY status to Central")

        # Activar modo de fallo manual - esto persiste hasta que se llame a recovery
        self.engine._manual_faulty_mode = True
        print("   ✓ Engine set to MANUAL FAULTY mode (persists until manual recovery)")

        # Enviar mensaje de fallo al Monitor
        if self.engine.monitor_server and self.engine.monitor_server.has_active_clients():
            failure_message = {
                MessageFields.TYPE: MessageTypes.HEALTH_CHECK_RESPONSE,
                MessageFields.MESSAGE_ID: str(uuid.uuid4()),  # ✅ 添加message_id以确保消息格式完整
                MessageFields.STATUS: ResponseStatus.SUCCESS,
                MessageFields.ENGINE_STATUS: "FAULTY",
                MessageFields.IS_CHARGING: self.engine.is_charging,
            }
            self.engine.monitor_server.send_broadcast_message(failure_message)
            print("   ✓ FAULTY signal sent to Monitor (via Socket)")

            # Si estamos cargando, detener la carga
            if self.engine.is_charging:
                print("   ✓ Charging interrupted due to failure")
                self.engine._stop_charging_session()
        else:
            print("⚠ No Monitor connected, cannot send FAULTY signal")

        print()
        print("   NOTE: Engine will remain in FAULTY mode until you use option [4]")
        print("         to simulate recovery. Health checks will continue to report FAULTY.")
        print("-" * 60)

    def _handle_simulate_recovery(self):
        """Simula la recuperación del Engine de una avería"""
        print("\n" + "-" * 60)
        print("✓ SIMULATING: Engine recovery from failure")
        print("   This will trigger Monitor to report ACTIVE status to Central")

        # Desactivar modo de fallo manual
        self.engine._manual_faulty_mode = False
        print("   ✓ Engine MANUAL FAULTY mode deactivated")

        # Enviar mensaje de recuperación al Monitor
        if self.engine.monitor_server and self.engine.monitor_server.has_active_clients():
            recovery_message = {
                MessageFields.TYPE: MessageTypes.HEALTH_CHECK_RESPONSE,
                MessageFields.MESSAGE_ID: str(uuid.uuid4()),  # ✅ 添加message_id以确保消息格式完整
                MessageFields.STATUS: ResponseStatus.SUCCESS,
                MessageFields.ENGINE_STATUS: "ACTIVE",
                MessageFields.IS_CHARGING: self.engine.is_charging,
            }
            self.engine.monitor_server.send_broadcast_message(recovery_message)
            print("   ✓ ACTIVE signal sent to Monitor (via Socket)")
            print()
            print("   Engine recovered! Health checks will now report ACTIVE status.")
        else:
            print("⚠ No Monitor connected, cannot send ACTIVE signal")

        print("-" * 60)

    def _show_status(self):
        """Muestra el estado actual del Engine"""
        print("\n" + "=" * 60)
        print("  CURRENT ENGINE STATUS")
        print("=" * 60)
        print(f"  CP ID: {self.engine.cp_id if self.engine.cp_id else 'Not initialized'}")

        status = self.engine.get_current_status()
        print(f"  Engine Status: {status}")
        if self.engine._manual_faulty_mode:
            print("  ⚠️  MANUAL FAULTY MODE: ACTIVE (use option [4] to recover)")

        print(f"  Running: {self.engine.running}")
        print(f"  Charging: {self.engine.is_charging}")

        if self.engine.monitor_server:
            print(f"  Monitor Server: Running on {self.engine.engine_listen_address[0]}:{self.engine.engine_listen_address[1]}")
            print(f"  Monitor Connected: {self.engine.monitor_server.has_active_clients()}")
        else:
            print("  Monitor Server: Not initialized")

        if self.engine.kafka_manager:
            print(f"  Kafka Connected: {self.engine.kafka_manager.is_connected()}")
        else:
            print("  Kafka: Not initialized")

        if self.engine.is_charging and self.engine.current_session:
            print("\n  CURRENT CHARGING SESSION:")
            print(f"    Session ID: {self.engine.current_session['session_id']}")
            print(f"    Driver ID: {self.engine.current_session['driver_id']}")
            print(f"    Duration: {time.time() - self.engine.current_session['start_time']:.1f}s")
            print(f"    Energy: {self.engine.current_session['energy_consumed_kwh']:.3f} kWh")
            print(f"    Cost: €{self.engine.current_session['total_cost']:.2f}")
            print(f"    Price: €{self.engine.current_session['price_per_kwh']}/kWh")

        print("=" * 60)
