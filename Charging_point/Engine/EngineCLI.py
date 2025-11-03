"""
CLI para el módulo Engine del Charging Point.
Permite simular las acciones físicas del usuario en el CP (enchufar/desenchufar vehículo, simular averías).
"""

import threading
import sys
import time


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
        print(f"  Status: {self.engine.get_current_status()}")
        print(f"  Charging: {'YES' if self.engine.is_charging else 'NO'}")

        if self.engine.is_charging and self.engine.current_session:
            print(f"  Session ID: {self.engine.current_session['session_id']}")
            print(f"  Driver ID: {self.engine.current_session['driver_id']}")
            print(f"  Energy: {self.engine.current_session['energy_consumed_kwh']:.3f} kWh")
            print(f"  Cost: €{self.engine.current_session['total_cost']:.2f}")

        print("-" * 60)
        print("  [1] Simulate vehicle connection (Start charging)")
        print("  [2] Simulate vehicle disconnection (Stop charging)")
        print("  [3] Simulate Engine failure (Send KO to Monitor)")
        print("  [4] Simulate Engine recovery (Send OK to Monitor)")
        print("  [5] Show current status")
        print("  [0] Exit menu (Engine continues running)")
        print("=" * 60)

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
                    self._handle_connect_vehicle()
                elif user_input == "2":
                    self._handle_disconnect_vehicle()
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

    def _handle_connect_vehicle(self):
        """Maneja la simulación de conexión del vehículo (enchufar)"""
        print("\n" + "-" * 60)

        if not self.engine.cp_id:
            print("❌ Cannot connect vehicle: CP_ID not initialized yet")
            print("   Wait for Monitor to provide CP_ID")
            print("-" * 60)
            return

        if self.engine.is_charging:
            print("⚠ Vehicle already connected and charging!")
            print(f"   Session ID: {self.engine.current_session['session_id']}")
            print(f"   Driver ID: {self.engine.current_session['driver_id']}")
            print("-" * 60)
            return

        # En un sistema real, esto se activaría cuando Central envíe start_charging_command
        # Aquí solo mostramos que el usuario "enchufó" el vehículo
        print("🔌 SIMULATING: Driver plugs vehicle into CP")
        print("   Waiting for Central authorization to start charging...")
        print("   (Charging will start automatically when Central sends command)")
        print("-" * 60)

    def _handle_disconnect_vehicle(self):
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
            print("   Final charging data sent to Central")
        else:
            print("❌ Failed to stop charging")

        print("-" * 60)

    def _handle_simulate_failure(self):
        """Simula una avería del Engine (según PDF página 11)"""
        print("\n" + "-" * 60)
        print("💥 SIMULATING: Engine hardware/software failure")
        print("   This will trigger Monitor to report FAULTY status to Central")

        # Enviar mensaje de fallo al Monitor
        if self.engine.monitor_server and self.engine.monitor_server.has_active_clients():
            failure_message = {
                "type": "health_check_response",
                "status": "KO",
                "cp_id": self.engine.cp_id,
                "reason": "Simulated hardware failure (manual trigger)"
            }
            self.engine.monitor_server.send_broadcast_message(failure_message)
            print("   KO signal sent to Monitor")

            # Si estamos cargando, detener la carga
            if self.engine.is_charging:
                print("   Charging interrupted due to failure")
                self.engine._stop_charging_session()
        else:
            print("⚠ No Monitor connected, cannot send KO signal")

        print("-" * 60)

    def _handle_simulate_recovery(self):
        """Simula la recuperación del Engine de una avería"""
        print("\n" + "-" * 60)
        print("✓ SIMULATING: Engine recovery from failure")
        print("   This will trigger Monitor to report ACTIVE status to Central")

        # Enviar mensaje de recuperación al Monitor
        if self.engine.monitor_server and self.engine.monitor_server.has_active_clients():
            recovery_message = {
                "type": "health_check_response",
                "status": "OK",
                "cp_id": self.engine.cp_id,
                "reason": "Recovered from failure (manual trigger)"
            }
            self.engine.monitor_server.send_broadcast_message(recovery_message)
            print("   OK signal sent to Monitor")
        else:
            print("⚠ No Monitor connected, cannot send OK signal")

        print("-" * 60)

    def _show_status(self):
        """Muestra el estado actual del Engine"""
        print("\n" + "=" * 60)
        print("  CURRENT ENGINE STATUS")
        print("=" * 60)
        print(f"  CP ID: {self.engine.cp_id if self.engine.cp_id else 'Not initialized'}")
        print(f"  Engine Status: {self.engine.get_current_status()}")
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
