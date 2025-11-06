"""
Monitor状态监控面板
Windows兼容的实时终端UI,用于显示Monitor的当前状态
使用os.system('cls')和colorama库实现跨平台兼容
"""

import os
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

try:
    from colorama import Fore, Back, Style, init

    # 初始化colorama以支持Windows
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    print("Warning: colorama not installed, will use no-color mode")
    print("Install command: pip install colorama")

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
        self.use_colors = COLORAMA_AVAILABLE

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
        os.system("cls" if os.name == "nt" else "clear")

    def _get_color(self, status: str) -> str:
        """根据状态返回颜色代码"""
        if not self.use_colors:
            return ""

        status_colors = {
            "ACTIVE": Fore.GREEN,
            "FAULTY": Fore.RED,
            "CHARGING": Fore.YELLOW,
            "DISCONNECTED": Fore.CYAN,
            "STOPPED": Fore.WHITE,
        }
        return status_colors.get(status, Fore.WHITE)

    def _reset_color(self) -> str:
        """重置颜色"""
        if not self.use_colors:
            return ""
        return Style.RESET_ALL

    def _run_panel(self):
        """运行面板主循环"""
        try:
            print("\nStarting Monitor status panel...")
            print("Press 1 to exit the panel\n")
            time.sleep(1)

            while self.running:
                try:
                    self._draw_panel()
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
            print("\nMonitor status panel exited")

    def _draw_panel(self):
        """绘制面板内容"""
        self._clear_screen()

        # 获取当前状态数据
        cp_id = self.monitor.args.id_cp
        current_status = self.monitor._current_status

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
        else:
            health_status = "No Response Received"

        # 绘制标题
        title = "=" * 80
        print(title)
        print(f"{'Monitor Status Panel':^80}")
        print(f"{'Charging Point ID: ' + cp_id:^80}")
        print(f"{'Update Time: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^80}")
        print(title)
        print()

        # 绘制充电桩状态
        status_color = self._get_color(current_status)
        print(f"【Charging Point Status】")
        print(f"  Current Status: {status_color}{current_status}{self._reset_color()}")
        print()

        # ✓  绘制组件状态（Central和Engine）
        print(f"【Component Status】")

        # Central状态判断
        if central_connected:
            if registered:
                central_component_status = "ACTIVE"
                central_status_color = self._get_color("ACTIVE")
            else:
                central_component_status = "CONNECTED (Not Registered)"
                central_status_color = Fore.YELLOW if self.use_colors else ""
        else:
            central_component_status = "DISCONNECTED"
            central_status_color = self._get_color("DISCONNECTED")

        # Engine状态判断
        if engine_connected:
            # 根据健康检查判断Engine状态
            if last_health_time and (
                time.time() - last_health_time < self.monitor.ENGINE_HEALTH_TIMEOUT
            ):
                engine_component_status = "ACTIVE"
                engine_status_color = self._get_color("ACTIVE")
            else:
                engine_component_status = "FAULTY (Health Check Timeout)"
                engine_status_color = self._get_color("FAULTY")
        else:
            engine_component_status = "DISCONNECTED"
            engine_status_color = self._get_color("DISCONNECTED")

        print(
            f"  Central:  {central_status_color}{central_component_status}{self._reset_color()}"
        )
        if self.monitor.central_conn_mgr:
            print(
                f"            Address: {self.monitor.args.ip_port_ev_central[0]}:{self.monitor.args.ip_port_ev_central[1]}"
            )

        print(
            f"  Engine:   {engine_status_color}{engine_component_status}{self._reset_color()}"
        )
        if self.monitor.engine_conn_mgr:
            print(
                f"            Address: {self.monitor.args.ip_port_ev_cp_e[0]}:{self.monitor.args.ip_port_ev_cp_e[1]}"
            )
        print()

        # 绘制认证和注册状态
        print(f"【Authentication & Registration】")
        auth_status = (
            f"{Fore.GREEN}Authenticated{self._reset_color()}"
            if authorized
            else (
                f"{Fore.RED}Not Authenticated{self._reset_color()}"
                if self.use_colors
                else ("Authenticated" if authorized else "Not Authenticated")
            )
        )
        reg_status = (
            f"{Fore.GREEN}Registered{self._reset_color()}"
            if registered
            else (
                f"{Fore.RED}Not Registered{self._reset_color()}"
                if self.use_colors
                else ("Registered" if registered else "Not Registered")
            )
        )

        print(f"  Auth Status: {auth_status}")
        print(f"  Registration Status: {reg_status}")
        print()

        # 绘制健康检查状态
        print(f"【Engine Health Check】")
        health_color = (
            Fore.GREEN
            if (last_health_time and time_since_health < 90) and self.use_colors
            else (Fore.RED if self.use_colors else "")
        )
        print(f"  Last Response: {health_color}{health_status}{self._reset_color()}")
        print(f"  Check Interval: {self.monitor.ENGINE_HEALTH_CHECK_INTERVAL}s")
        print(f"  Timeout Threshold: {self.monitor.ENGINE_HEALTH_TIMEOUT}s")
        print()

        # 绘制心跳状态
        print(f"【Central Heartbeat】")
        heartbeat_running = (
            self.monitor._heartbeat_thread and self.monitor._heartbeat_thread.is_alive()
        )
        heartbeat_status = (
            f"{Fore.GREEN}Running{self._reset_color()}"
            if heartbeat_running and self.use_colors
            else ("Running" if heartbeat_running else "Stopped")
        )
        print(f"  Heartbeat Status: {heartbeat_status}")
        print(f"  Heartbeat Interval: {self.monitor.HEARTBEAT_INTERVAL}s")
        print()

        # 绘制系统信息
        print(f"【System Information】")
        print(f"  Monitor Running: {'Yes' if self.monitor.running else 'No'}")
        print(f"  Main Thread: {threading.main_thread().name}")
        print(f"  Active Threads: {threading.active_count()}")
        print()

        # 绘制底部提示
        print("=" * 80)
        print(f"{'Tip: Press Ctrl+C to exit the panel':^80}")
        print("=" * 80)

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
        print("=" * 60)
        print(" Press Ctrl+C to exit")
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
        print("Starting panel... (Press Ctrl+C to exit)")
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
