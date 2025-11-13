"""
Monitor状态监控面板
Windows兼容的实时终端UI,用于显示Monitor的当前状态
使用Rich库实现跨平台兼容的美化显示
"""

import os
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich.live import Live
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: rich not installed, will use simple mode")
    print("Install command: pip install rich")

if TYPE_CHECKING:
    from Charging_point.Monitor.EC_CP_M import EV_CP_M


class MonitorStatusPanel:
    """Monitor实时状态监控面板 - Windows兼容版本"""

    def __init__(self, monitor: "EV_CP_M"):
        """
        初始化Monitor状态面板

        Args:
            monitor: EV_CP_M实例
        """
        self.monitor = monitor
        self.logger = monitor.logger
        self.running = False
        self.panel_thread = None
        self.update_interval = 1  # 刷新间隔(秒)
        self.use_rich = RICH_AVAILABLE
        if self.use_rich:
            self.console = Console()

    def start(self):
        """启动状态面板"""
        if self.running:
            self.logger.warning("Monitor status panel is already running")
            return

        self.running = True
        self.panel_thread = threading.Thread(target=self._run_panel, daemon=True)
        self.panel_thread.start()
        self.logger.debug("Monitor status panel started")

    def stop(self):
        """停止状态面板"""
        self.running = False
        if self.panel_thread:
            self.panel_thread.join(timeout=2)
        # 清屏后显示退出消息
        self._clear_screen()

        self.logger.debug("Monitor status panel stopped")

    def _clear_screen(self):
        """清屏 - Windows/Linux兼容"""
        if self.use_rich:
            self.console.clear()
        else:
            os.system("cls" if os.name == "nt" else "clear")

    def _get_status_color(self, status: str) -> str:
        """根据状态返回Rich颜色代码（使用全局主题）"""
        from Common.Config.ConsolePrinter import ConsolePrinter
        theme = ConsolePrinter.get_theme()
        
        status_color_map = {
            "ACTIVE": theme.get("status_active", "dim"),
            "FAULTY": theme.get("status_faulty", "dim"),
            "CHARGING": theme.get("status_charging", "dim"),
            "DISCONNECTED": theme.get("status_disconnected", "dim"),
            "STOPPED": theme.get("status_stopped", "dim"),
        }
        return status_color_map.get(status, "dim")

    def _run_panel(self):
        """运行面板主循环"""
        try:
            if self.use_rich:
                self.console.print("[bold blue]Starting Monitor status panel...[/bold blue]")
                self.console.print("[dim]Press 1 to exit the panel[/dim]\n")
            else:
                print("\nStarting Monitor status panel...")
                print("Press 1 to exit the panel\n")
            time.sleep(1)

            if self.use_rich:
                # 使用Rich的Live功能实现实时更新
                with Live(self._create_rich_panel(), refresh_per_second=1, screen=True) as live:
                    while self.running:
                        try:
                            live.update(self._create_rich_panel())
                            time.sleep(self.update_interval)
                        except KeyboardInterrupt:
                            self.logger.debug("Keyboard interrupt detected, stopping panel...")
                            self.running = False
                            break
                        except Exception as e:
                            self.logger.error(f"Error drawing panel: {e}")
                            time.sleep(2)
            else:
                # 降级到简单模式
                while self.running:
                    try:
                        self._draw_simple_panel()
                        time.sleep(self.update_interval)
                    except KeyboardInterrupt:
                        self.logger.debug("Keyboard interrupt detected, stopping panel...")
                        self.running = False
                        break
                    except Exception as e:
                        self.logger.error(f"Error drawing panel: {e}")
                        time.sleep(2)

        except Exception as e:
            self.logger.error(f"Monitor status panel runtime error: {e}")
        finally:
            self._clear_screen()
            if self.use_rich:
                self.console.print("\n[bold]Monitor status panel exited[/bold]")
            else:
                print("\nMonitor status panel exited")

    def _create_rich_panel(self):
        """创建Rich格式的面板内容"""
        # 获取当前状态数据
        cp_id = self.monitor.args.id_cp
        current_status = self.monitor._current_status
        status_color = self._get_status_color(current_status)

        # 连接状态
        central_connected = (
            self.monitor.central_conn_mgr.is_connected
            if self.monitor.central_conn_mgr
            else False
        )
        engine_connected = (
            self.monitor.engine_conn_mgr.is_connected
            if self.monitor.engine_conn_mgr
            else False
        )

        # 认证和注册状态
        authorized = self.monitor._authorized
        registered = self.monitor._registration_confirmed

        # 健康检查状态
        last_health_time = self.monitor._last_health_response_time
        if last_health_time:
            time_since_health = time.time() - last_health_time
            health_status = (
                f"{time_since_health:.1f}s ago"
                if time_since_health < 90
                else f"Timeout ({time_since_health:.1f}s ago)"
            )
            health_color = "green" if time_since_health < 90 else "red"
        else:
            health_status = "No Response Received"
            health_color = "red"

        # 心跳状态
        heartbeat_running = (
            self.monitor._heartbeat_thread and self.monitor._heartbeat_thread.is_alive()
        )

        # 获取全局主题配置
        from Common.Config.ConsolePrinter import ConsolePrinter
        theme = ConsolePrinter.get_theme()
        
        # 构建面板内容
        content_parts = []
        
        # 标题
        title_style = theme.get("panel_title", "bold")
        content_parts.append(f"[{title_style}]{'Monitor Status Panel':^80}[/{title_style}]")
        content_parts.append(f"[{title_style}]Charging Point ID:[/{title_style}] {cp_id}")
        content_parts.append(f"[{title_style}]Update Time:[/{title_style}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content_parts.append("")
        
        # 充电桩状态
        section_style = theme.get("section_title", "bold")
        status_style = self._get_status_color(current_status)
        content_parts.append(f"[{section_style}]Charging Point Status[/{section_style}]")
        content_parts.append(f"  Current Status: [{status_style}]{current_status}[/{status_style}]")
        content_parts.append("")
        
        # 组件状态
        content_parts.append(f"[{section_style}]Component Status[/{section_style}]")
        
        # Central状态
        if central_connected:
            if registered:
                central_status_style = theme.get("status_active", "dim")
                central_status_text = f"[{central_status_style}]ACTIVE[/{central_status_style}]"
            else:
                central_status_style = theme.get("warning", "dim")
                central_status_text = f"[{central_status_style}]CONNECTED (Not Registered)[/{central_status_style}]"
        else:
            central_status_style = theme.get("status_disconnected", "dim")
            central_status_text = f"[{central_status_style}]DISCONNECTED[/{central_status_style}]"
        
        content_parts.append(f"  Central: {central_status_text}")
        if self.monitor.central_conn_mgr:
            content_parts.append(f"    Address: {self.monitor.args.ip_port_ev_central[0]}:{self.monitor.args.ip_port_ev_central[1]}")
        
        # Engine状态
        if engine_connected:
            if last_health_time and (time.time() - last_health_time < self.monitor.ENGINE_HEALTH_TIMEOUT):
                engine_status_style = theme.get("status_active", "dim")
                engine_status_text = f"[{engine_status_style}]ACTIVE[/{engine_status_style}]"
            else:
                engine_status_style = theme.get("status_faulty", "dim")
                engine_status_text = f"[{engine_status_style}]FAULTY (Health Check Timeout)[/{engine_status_style}]"
        else:
            engine_status_style = theme.get("status_disconnected", "dim")
            engine_status_text = f"[{engine_status_style}]DISCONNECTED[/{engine_status_style}]"
        
        content_parts.append(f"  Engine: {engine_status_text}")
        if self.monitor.engine_conn_mgr:
            content_parts.append(f"    Address: {self.monitor.args.ip_port_ev_cp_e[0]}:{self.monitor.args.ip_port_ev_cp_e[1]}")
        content_parts.append("")
        
        # 认证和注册
        content_parts.append(f"[{section_style}]Authentication & Registration[/{section_style}]")
        info_style = theme.get("info", "dim")
        auth_text = f"[{info_style}]Authenticated[/{info_style}]" if authorized else f"[{info_style}]Not Authenticated[/{info_style}]"
        reg_text = f"[{info_style}]Registered[/{info_style}]" if registered else f"[{info_style}]Not Registered[/{info_style}]"
        content_parts.append(f"  Auth Status: {auth_text}")
        content_parts.append(f"  Registration Status: {reg_text}")
        content_parts.append("")
        
        # 健康检查
        content_parts.append(f"[{section_style}]Engine Health Check[/{section_style}]")
        health_style = "dim" if health_color == "green" else theme.get("error", "dim")
        content_parts.append(f"  Last Response: [{health_style}]{health_status}[/{health_style}]")
        content_parts.append(f"  Check Interval: {self.monitor.ENGINE_HEALTH_CHECK_INTERVAL}s")
        content_parts.append(f"  Timeout Threshold: {self.monitor.ENGINE_HEALTH_TIMEOUT}s")
        content_parts.append("")
        
        # 心跳
        content_parts.append(f"[{section_style}]Central Heartbeat[/{section_style}]")
        heartbeat_style = theme.get("success", "dim") if heartbeat_running else theme.get("error", "dim")
        heartbeat_text = f"[{heartbeat_style}]Running[/{heartbeat_style}]" if heartbeat_running else f"[{heartbeat_style}]Stopped[/{heartbeat_style}]"
        content_parts.append(f"  Heartbeat Status: {heartbeat_text}")
        content_parts.append(f"  Heartbeat Interval: {self.monitor.HEARTBEAT_INTERVAL}s")
        content_parts.append("")
        
        # 充电数据（如果正在充电）
        if self.monitor._current_charging_data and current_status == "CHARGING":
            charging_data = self.monitor._current_charging_data
            content_parts.append(f"[{section_style}]Current Charging Session[/{section_style}]")
            charging_style = theme.get("status_charging", "dim")
            
            session_id = charging_data.get("session_id", "N/A")
            # 截断过长的session_id以便显示
            if len(session_id) > 30:
                session_id = session_id[:27] + "..."
            
            driver_id = charging_data.get("driver_id", "unknown")
            energy = charging_data.get("energy_consumed_kwh", 0.0)
            cost = charging_data.get("total_cost", 0.0)
            start_time = charging_data.get("start_time", time.time())
            duration = time.time() - start_time
            
            content_parts.append(f"  Session ID: [{charging_style}]{session_id}[/{charging_style}]")
            content_parts.append(f"  Driver ID: [{charging_style}]{driver_id}[/{charging_style}]")
            content_parts.append(f"  Duration: [{charging_style}]{duration:.1f}s[/{charging_style}]")
            content_parts.append(f"  Energy Consumed: [{charging_style}]{energy:.3f} kWh[/{charging_style}]")
            content_parts.append(f"  Total Cost: [{charging_style}]€{cost:.2f}[/{charging_style}]")
            
                        
            last_update = charging_data.get("last_update", time.time())
            time_since_update = time.time() - last_update
            if time_since_update < 5:
                update_style = theme.get("success", "dim")
            elif time_since_update < 10:
                update_style = theme.get("warning", "dim")
            else:
                update_style = theme.get("error", "dim")
            content_parts.append(f"  Last Update: [{update_style}]{time_since_update:.1f}s ago[/{update_style}]")
            content_parts.append("")
        
        # 系统信息
        content_parts.append(f"[{section_style}]System Information[/{section_style}]")
        content_parts.append(f"  Monitor Running: {'Yes' if self.monitor.running else 'No'}")
        content_parts.append(f"  Main Thread: {threading.main_thread().name}")
        content_parts.append(f"  Active Threads: {threading.active_count()}")
        content_parts.append("")
        separator_style = theme.get("separator", "dim")
        content_parts.append(f"[{separator_style}]Tip: Press 1 to exit the panel[/{separator_style}]")
        
        # 创建面板
        panel_content = "\n".join(content_parts)
        border_style = theme.get("panel_border", "dim")
        return Panel(panel_content, title="Monitor Status Panel", box=box.ROUNDED, border_style=border_style)

    def _draw_panel(self):
        """绘制面板内容（已废弃，使用_create_rich_panel代替）"""
        # 此方法已废弃，保留仅为向后兼容
        pass

    def _draw_simple_panel(self):
        """绘制简化版面板(当colorama不可用时)"""
        self._clear_screen()

        cp_id = self.monitor.args.id_cp
        current_status = self.monitor._current_status
        central_connected = (
            self.monitor.central_conn_mgr.is_connected
            if self.monitor.central_conn_mgr
            else False
        )
        engine_connected = (
            self.monitor.engine_conn_mgr.is_connected
            if self.monitor.engine_conn_mgr
            else False
        )

        print("=" * 60)
        print(f" Monitor Status Panel")
        print(f" Charging Point ID: {cp_id}")
        print(f" Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()
        print(f"Charging Point Status: {current_status}")
        print(f"Central Connection: {'Connected' if central_connected else 'Disconnected'}")
        print(f"Engine Connection: {'Connected' if engine_connected else 'Disconnected'}")
        print()
        
        # 显示充电数据（如果正在充电）
        if self.monitor._current_charging_data and current_status == "CHARGING":
            charging_data = self.monitor._current_charging_data
            print("-" * 60)
            print(" Current Charging Session:")
            print(f"  Session ID: {charging_data.get('session_id', 'N/A')[:30]}")
            print(f"  Driver ID: {charging_data.get('driver_id', 'unknown')}")
            duration = time.time() - charging_data.get("start_time", time.time())
            print(f"  Duration: {duration:.1f}s")
            print(f"  Energy: {charging_data.get('energy_consumed_kwh', 0.0):.3f} kWh")
            print(f"  Cost: €{charging_data.get('total_cost', 0.0):.2f}")
            if duration > 0:
                charging_rate = charging_data.get('energy_consumed_kwh', 0.0) / duration * 3600
                print(f"  Rate: {charging_rate:.2f} kWh/h")
            print("-" * 60)
            print()
        
        print("=" * 60)
        print(" Press 1 to exit")
        print("=" * 60)


def test_panel():
    """测试函数 - 用于独立测试面板"""
    from unittest.mock import Mock

    print("Monitor status panel test")
    print("=" * 60)

    # 创建模拟的Monitor对象
    mock_monitor = Mock()
    mock_monitor.args = Mock()
    mock_monitor.args.id_cp = "CP_TEST_001"
    mock_monitor.args.ip_port_ev_central = ("127.0.0.1", 8000)
    mock_monitor.args.ip_port_ev_cp_e = ("127.0.0.1", 8001)

    mock_monitor._current_status = "ACTIVE"
    mock_monitor._authorized = True
    mock_monitor._registration_confirmed = True
    mock_monitor._last_health_response_time = time.time()
    mock_monitor.running = True

    mock_monitor.HEARTBEAT_INTERVAL = 30
    mock_monitor.ENGINE_HEALTH_CHECK_INTERVAL = 30
    mock_monitor.ENGINE_HEALTH_TIMEOUT = 90

    # 模拟连接管理器
    mock_monitor.central_conn_mgr = Mock()
    mock_monitor.central_conn_mgr.is_connected = True

    mock_monitor.engine_conn_mgr = Mock()
    mock_monitor.engine_conn_mgr.is_connected = True

    # 模拟线程
    mock_monitor._heartbeat_thread = Mock()
    mock_monitor._heartbeat_thread.is_alive.return_value = True

    mock_monitor.logger = Mock()

    # 创建并启动面板
    panel = MonitorStatusPanel(mock_monitor)

    try:
        print("Starting panel... (Press 1 to exit)")
        time.sleep(2)
        panel.start()

        # 等待用户中断
        while panel.running:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nInterrupt detected, stopping...")
        panel.stop()
    except Exception as e:
        print(f"\nError: {e}")
        panel.stop()


if __name__ == "__main__":
    test_panel()
