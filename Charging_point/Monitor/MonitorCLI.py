"""
CLI para el módulo Monitor del Charging Point.
Permite controlar el Monitor y mostrar/ocultar el panel de estado en tiempo real.
"""

import threading
import sys
import os

# Añadir el directorio raíz al path para imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Config.ConsolePrinter import get_printer


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
        self.printer = get_printer()

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
        # 构建状态信息
        status_info = []
        status_info.append(f"CP ID: {self.monitor.args.id_cp}")
        status_info.append(f"Status: {self.monitor._current_status}")

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

        status_info.append(f"Central: {central_status}")
        status_info.append(f"Engine:  {engine_status}")

        # Estado de autenticación y registro
        auth_status = "✓ Authorized" if self.monitor._authorized else "✗ Not authorized"
        reg_status = (
            "✓ Registered"
            if self.monitor._registration_confirmed
            else "✗ Not registered"
        )

        status_info.append(f"Auth:    {auth_status}")
        status_info.append(f"Reg:     {reg_status}")

        # 显示状态面板
        self.printer.print_panel("\n".join(status_info), title="Current Status", style="cyan")
        
        # 显示菜单
        panel_status = "VISIBLE" if self.panel_active else "HIDDEN"
        menu_items = {
            "PANEL CONTROL": [
                f"[1] Toggle Status Panel (Current: {panel_status})"
            ],
            "INFORMATION": [
                "[2] Show current status summary",
                "[3] Show connection details"
            ]
        }
        self.printer.print_menu("EV_CP_M - MONITOR CONTROL MENU", menu_items)

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
                    self.printer.print_warning(f"Unknown command: {user_input}")
                    self.printer.print_info("Press ENTER to show menu")

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
            self.printer.print_info("Status panel HIDDEN. Press ENTER to show menu.")
        else:
            # Mostrar panel
            self._show_panel()

    def _show_panel(self):
        """Muestra el panel de estado"""
        if not self.monitor.enable_panel:
            self.printer.print_error("Panel is disabled. Cannot show panel.")
            self.printer.print_info("Start Monitor with --panel flag to enable panel.")
            return

        if self.panel_active:
            self.printer.print_warning("Panel is already visible.")
            return

        try:
            # Inicializar el panel si no existe
            if not self.monitor.status_panel:
                from Charging_point.Monitor.MonitorStatusPanel import MonitorStatusPanel

                self.monitor.status_panel = MonitorStatusPanel(self.monitor)

            # Iniciar el panel
            self.monitor.status_panel.start()
            self.panel_active = True
            self.printer.print_success("Status panel is now VISIBLE")
            self.printer.print_info("Press 1 in the panel to return to CLI menu")

        except ImportError as e:
            self.printer.print_error(f"Cannot import MonitorStatusPanel: {e}")
            self.printer.print_info("Make sure MonitorStatusPanel.py exists")
        except Exception as e:
            self.printer.print_error(f"Failed to show panel: {e}")

    def _hide_panel(self):
        """Oculta el panel de estado"""
        if not self.panel_active:
            self.printer.print_warning("Panel is already hidden.")
            return

        try:
            if self.monitor.status_panel:
                self.monitor.status_panel.stop()
                self.panel_active = False
                self.printer.print_success("Status panel is now HIDDEN")
        except Exception as e:
            self.printer.print_error(f"Failed to hide panel: {e}")

    def _show_status_summary(self):
        """Muestra un resumen del estado actual"""
        # 构建状态摘要
        summary = []
        summary.append(f"Charging Point ID: {self.monitor.args.id_cp}")
        summary.append(f"Current Status:    {self.monitor._current_status}")
        summary.append("\nCONNECTIONS:")

        # Central
        central_connected = (
            self.monitor.central_conn_mgr and self.monitor.central_conn_mgr.is_connected
        )
        central_addr = f"{self.monitor.args.ip_port_ev_central[0]}:{self.monitor.args.ip_port_ev_central[1]}"
        summary.append(f"  Central: {'✓ Connected' if central_connected else '✗ Disconnected'} ({central_addr})")

        # Engine
        engine_connected = (
            self.monitor.engine_conn_mgr and self.monitor.engine_conn_mgr.is_connected
        )
        engine_addr = f"{self.monitor.args.ip_port_ev_cp_e[0]}:{self.monitor.args.ip_port_ev_cp_e[1]}"
        summary.append(f"  Engine:  {'✓ Connected' if engine_connected else '✗ Disconnected'} ({engine_addr})")

        summary.append("\nAUTHENTICATION & REGISTRATION:")
        summary.append(f"  Authorized: {'✓ Yes' if self.monitor._authorized else '✗ No'}")
        summary.append(f"  Registered: {'✓ Yes' if self.monitor._registration_confirmed else '✗ No'}")

        summary.append("\nHEALTH CHECK:")
        if self.monitor._last_health_response_time:
            import time
            elapsed = time.time() - self.monitor._last_health_response_time
            summary.append(f"  Last Engine response: {elapsed:.1f}s ago")
        else:
            summary.append("  Last Engine response: Never")

        self.printer.print_panel("\n".join(summary), title="STATUS SUMMARY", style="blue")

    def _show_connection_details(self):
        """Muestra detalles de las conexiones"""
        # 构建连接详情
        details = []
        
        # Central Connection
        details.append("CENTRAL CONNECTION:")
        details.append(f"  Address: {self.monitor.args.ip_port_ev_central[0]}:{self.monitor.args.ip_port_ev_central[1]}")
        if self.monitor.central_conn_mgr:
            details.append(f"  Connected: {'Yes' if self.monitor.central_conn_mgr.is_connected else 'No'}")
            details.append(f"  Heartbeat Interval: {self.monitor.HEARTBEAT_INTERVAL}s")
            heartbeat_running = (
                self.monitor._heartbeat_thread
                and self.monitor._heartbeat_thread.is_alive()
            )
            details.append(f"  Heartbeat Thread: {'Running' if heartbeat_running else 'Stopped'}")
        else:
            details.append("  Connection Manager: Not initialized")

        details.append("\nENGINE CONNECTION:")
        details.append(f"  Address: {self.monitor.args.ip_port_ev_cp_e[0]}:{self.monitor.args.ip_port_ev_cp_e[1]}")
        if self.monitor.engine_conn_mgr:
            details.append(f"  Connected: {'Yes' if self.monitor.engine_conn_mgr.is_connected else 'No'}")
            details.append(f"  Health Check Interval: {self.monitor.ENGINE_HEALTH_CHECK_INTERVAL}s")
            details.append(f"  Health Check Timeout: {self.monitor.ENGINE_HEALTH_TIMEOUT}s")
            health_running = (
                self.monitor._engine_health_thread
                and self.monitor._engine_health_thread.is_alive()
            )
            details.append(f"  Health Check Thread: {'Running' if health_running else 'Stopped'}")

            if self.monitor._last_health_response_time:
                import time
                elapsed = time.time() - self.monitor._last_health_response_time
                status = (
                    "OK" if elapsed < self.monitor.ENGINE_HEALTH_TIMEOUT else "TIMEOUT"
                )
                details.append(f"  Last Health Response: {elapsed:.1f}s ago ({status})")
            else:
                details.append("  Last Health Response: Never")
        else:
            details.append("  Connection Manager: Not initialized")

        self.printer.print_panel("\n".join(details), title="CONNECTION DETAILS", style="green")
