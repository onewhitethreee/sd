"""
CLI para el módulo Monitor del Charging Point.
Permite controlar el Monitor y mostrar/ocultar el panel de estado en tiempo real.
"""

import threading
import sys
import os

# Añadir el directorio raíz al path para imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


class MonitorCLI:
    def __init__(self, monitor, logger):
        """
        Inicializa el CLI del Monitor.

        Args:
            monitor: Instancia de EV_CP_M
            logger: Logger para mostrar mensajes
        """
        self.monitor = monitor
        self.logger = logger
        self.running = False
        self.cli_thread = None
        self.panel_active = False  # Controla si el panel está activo

    def start(self):
        """Inicia el CLI en un hilo separado"""
        if self.cli_thread and self.cli_thread.is_alive():
            self.logger.warning("CLI already running")
            return

        self.running = True
        self.cli_thread = threading.Thread(
            target=self._run_cli, daemon=True, name="MonitorCLI"
        )
        self.cli_thread.start()
        self.logger.info("Monitor CLI started")

    def stop(self):
        """Detiene el CLI"""
        self.running = False
        if self.cli_thread:
            self.logger.info("Monitor CLI stopped")

    def _show_menu(self):
        """Muestra el menú del CLI"""
        print("\n" + "=" * 60)
        print("  EV_CP_M - MONITOR CONTROL MENU")
        print("=" * 60)
        print(f"  CP ID: {self.monitor.args.id_cp}")
        print(f"  Status: {self.monitor._current_status}")

        # Estado de conexiones
        central_status = (
            "✓ Connected"
            if (
                self.monitor.central_conn_mgr
                and self.monitor.central_conn_mgr.is_connected
            )
            else "✗ Disconnected"
        )
        engine_status = (
            "✓ Connected"
            if (
                self.monitor.engine_conn_mgr
                and self.monitor.engine_conn_mgr.is_connected
            )
            else "✗ Disconnected"
        )

        print(f"  Central: {central_status}")
        print(f"  Engine:  {engine_status}")

        # Estado de autenticación y registro
        auth_status = "✓ Authorized" if self.monitor._authorized else "✗ Not authorized"
        reg_status = (
            "✓ Registered"
            if self.monitor._registration_confirmed
            else "✗ Not registered"
        )

        print(f"  Auth:    {auth_status}")
        print(f"  Reg:     {reg_status}")

        print("-" * 60)
        print("  PANEL CONTROL:")
        panel_status = "VISIBLE" if self.panel_active else "HIDDEN"
        print(f"  [1] Toggle Status Panel (Current: {panel_status})")
        print()
        print("  INFORMATION:")
        print("  [2] Show current status summary")
        print("  [3] Show connection details")
        print()
        print("=" * 60)

    def _run_cli(self):
        """Ejecuta el loop principal del CLI"""
        self.logger.info("Monitor CLI ready. Press ENTER to show menu...")

        while self.running and self.monitor.running:
            try:
                # Esperar input del usuario
                user_input = input().strip()

                # Si presiona ENTER sin input, mostrar menú
                if not user_input:
                    self._show_menu()
                    continue

                if user_input == "1":
                    self._toggle_panel()
                elif user_input == "2":
                    self._show_status_summary()
                elif user_input == "3":
                    self._show_connection_details()
                else:
                    print(f"Unknown command: {user_input}")
                    print("Press ENTER to show menu")

            except EOFError:
                # Input cerrado (ej. Ctrl+D)
                break
            except Exception as e:
                self.logger.error(f"Error in CLI loop: {e}")

    def _toggle_panel(self):
        """Alterna entre mostrar y ocultar el panel de estado"""
        if self.panel_active:
            # Ocultar panel
            self._hide_panel()
            print("Status panel HIDDEN. Press ENTER to show menu.")
        else:
            # Mostrar panel
            self._show_panel()

    def _show_panel(self):
        """Muestra el panel de estado"""
        if not self.monitor.enable_panel:
            print("❌ Panel is disabled. Cannot show panel.")
            print("   Start Monitor with --panel flag to enable panel.")
            return

        if self.panel_active:
            print("⚠️  Panel is already visible.")
            return

        try:
            # Inicializar el panel si no existe
            if not self.monitor.status_panel:
                from Charging_point.Monitor.MonitorStatusPanel import MonitorStatusPanel

                self.monitor.status_panel = MonitorStatusPanel(self.monitor)

            # Iniciar el panel
            self.monitor.status_panel.start()
            self.panel_active = True
            print("✓ Status panel is now VISIBLE")
            print("  Press Ctrl+C in the panel to return to CLI menu")

        except ImportError as e:
            print(f"❌ Cannot import MonitorStatusPanel: {e}")
            print("   Make sure MonitorStatusPanel.py exists")
        except Exception as e:
            print(f"❌ Failed to show panel: {e}")

    def _hide_panel(self):
        """Oculta el panel de estado"""
        if not self.panel_active:
            print("⚠️  Panel is already hidden.")
            return

        try:
            if self.monitor.status_panel:
                self.monitor.status_panel.stop()
                self.panel_active = False
                print("✓ Status panel is now HIDDEN")
        except Exception as e:
            print(f"❌ Failed to hide panel: {e}")

    def _show_status_summary(self):
        """Muestra un resumen del estado actual"""
        print("\n" + "=" * 60)
        print("  STATUS SUMMARY")
        print("=" * 60)
        print(f"  Charging Point ID: {self.monitor.args.id_cp}")
        print(f"  Current Status:    {self.monitor._current_status}")
        print()
        print("  CONNECTIONS:")

        # Central
        central_connected = (
            self.monitor.central_conn_mgr and self.monitor.central_conn_mgr.is_connected
        )
        central_addr = f"{self.monitor.args.ip_port_ev_central[0]}:{self.monitor.args.ip_port_ev_central[1]}"
        print(
            f"    Central: {'✓ Connected' if central_connected else '✗ Disconnected'} ({central_addr})"
        )

        # Engine
        engine_connected = (
            self.monitor.engine_conn_mgr and self.monitor.engine_conn_mgr.is_connected
        )
        engine_addr = f"{self.monitor.args.ip_port_ev_cp_e[0]}:{self.monitor.args.ip_port_ev_cp_e[1]}"
        print(
            f"    Engine:  {'✓ Connected' if engine_connected else '✗ Disconnected'} ({engine_addr})"
        )

        print()
        print("  AUTHENTICATION & REGISTRATION:")
        print(f"    Authorized: {'✓ Yes' if self.monitor._authorized else '✗ No'}")
        print(
            f"    Registered: {'✓ Yes' if self.monitor._registration_confirmed else '✗ No'}"
        )

        print()
        print("  HEALTH CHECK:")
        if self.monitor._last_health_response_time:
            import time

            elapsed = time.time() - self.monitor._last_health_response_time
            print(f"    Last Engine response: {elapsed:.1f}s ago")
        else:
            print(f"    Last Engine response: Never")

        print("=" * 60)

    def _show_connection_details(self):
        """Muestra detalles de las conexiones"""
        print("\n" + "=" * 60)
        print("  CONNECTION DETAILS")
        print("=" * 60)

        # Central Connection
        print("  CENTRAL CONNECTION:")
        print(
            f"    Address: {self.monitor.args.ip_port_ev_central[0]}:{self.monitor.args.ip_port_ev_central[1]}"
        )
        if self.monitor.central_conn_mgr:
            print(
                f"    Connected: {'Yes' if self.monitor.central_conn_mgr.is_connected else 'No'}"
            )
            print(f"    Heartbeat Interval: {self.monitor.HEARTBEAT_INTERVAL}s")
            heartbeat_running = (
                self.monitor._heartbeat_thread
                and self.monitor._heartbeat_thread.is_alive()
            )
            print(
                f"    Heartbeat Thread: {'Running' if heartbeat_running else 'Stopped'}"
            )
        else:
            print("    Connection Manager: Not initialized")

        print()

        # Engine Connection
        print("  ENGINE CONNECTION:")
        print(
            f"    Address: {self.monitor.args.ip_port_ev_cp_e[0]}:{self.monitor.args.ip_port_ev_cp_e[1]}"
        )
        if self.monitor.engine_conn_mgr:
            print(
                f"    Connected: {'Yes' if self.monitor.engine_conn_mgr.is_connected else 'No'}"
            )
            print(
                f"    Health Check Interval: {self.monitor.ENGINE_HEALTH_CHECK_INTERVAL}s"
            )
            print(f"    Health Check Timeout: {self.monitor.ENGINE_HEALTH_TIMEOUT}s")
            health_running = (
                self.monitor._engine_health_thread
                and self.monitor._engine_health_thread.is_alive()
            )
            print(
                f"    Health Check Thread: {'Running' if health_running else 'Stopped'}"
            )

            if self.monitor._last_health_response_time:
                import time

                elapsed = time.time() - self.monitor._last_health_response_time
                status = (
                    "OK" if elapsed < self.monitor.ENGINE_HEALTH_TIMEOUT else "TIMEOUT"
                )
                print(f"    Last Health Response: {elapsed:.1f}s ago ({status})")
            else:
                print(f"    Last Health Response: Never")
        else:
            print("    Connection Manager: Not initialized")

        print("=" * 60)


