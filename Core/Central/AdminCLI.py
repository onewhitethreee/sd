"""
管理员交互式命令行界面
用于Central系统的管理操作
"""

import threading
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Core.Central.EV_Central import EV_Central


class AdminCLI:
    """管理员命令行接口"""

    def __init__(self, central: "EV_Central"):
        """
        初始化管理员CLI

        Args:
            central: EV_Central实例
        """
        self.central = central
        self.running = False
        self.cli_thread = None
        self.logger = central.logger

    def start(self):
        """启动交互式命令行界面"""
        if self.running:
            self.logger.warning("管理员CLI已经在运行中")
            return

        self.running = True
        self.cli_thread = threading.Thread(target=self._run_cli, daemon=True)
        self.cli_thread.start()
        self.logger.info("管理员CLI已启动")

    def stop(self):
        """停止交互式命令行界面"""
        self.running = False
        if self.cli_thread:
            self.cli_thread.join(timeout=2)
        self.logger.info("管理员CLI已停止")

    def _run_cli(self):
        """运行交互式命令循环"""
        self._print_help()

        while self.running:
            try:
                command = input("\nAdmin> ").strip()
                if not command:
                    continue

                self._process_command(command)

            except KeyboardInterrupt:
                print("\n检测到中断，使用 'quit' 命令退出")
                continue
            except EOFError:
                break
            except Exception as e:
                self.logger.error(f"处理命令时出错: {e}")
                print(f"错误: {e}")

    

    def _print_help(self):
        """打印帮助信息"""
        help_text = """
可用命令:
  list                    - 列出所有充电桩及其状态
  list available          - 列出所有可用的充电桩
  list active             - 列出所有活跃的充电桩
  list sessions           - 列出所有充电会话

  stop <cp_id>           - 停止指定的充电桩
  stop all               - 停止所有充电桩

  resume <cp_id>         - 恢复指定的充电桩
  resume all             - 恢复所有充电桩

  status <cp_id>         - 查看指定充电桩的详细状态
  session <session_id>   - 查看指定充电会话的详细信息

  stats                  - 显示系统统计信息
  help                   - 显示此帮助信息
  quit                   - 退出管理员控制台
"""
        print(help_text)

    def _process_command(self, command: str):
        """
        处理用户输入的命令

        Args:
            command: 用户输入的命令字符串
        """
        parts = command.lower().split()
        if not parts:
            return

        cmd = parts[0]

        try:
            if cmd == "help":
                self._print_help()

            elif cmd == "quit" or cmd == "exit":
                print("退出管理员控制台...")
                self.running = False

            elif cmd == "list":
                subcommand = parts[1] if len(parts) > 1 else None
                self._handle_list_command(subcommand)

            elif cmd == "stop":
                if len(parts) < 2:
                    print("错误: 请指定充电桩ID或使用 'all'")
                    print("用法: stop <cp_id> 或 stop all")
                else:
                    cp_id = parts[1]
                    self._handle_stop_command(cp_id)

            elif cmd == "resume":
                if len(parts) < 2:
                    print("错误: 请指定充电桩ID或使用 'all'")
                    print("用法: resume <cp_id> 或 resume all")
                else:
                    cp_id = parts[1]
                    self._handle_resume_command(cp_id)

            elif cmd == "status":
                if len(parts) < 2:
                    print("错误: 请指定充电桩ID")
                    print("用法: status <cp_id>")
                else:
                    cp_id = parts[1]
                    self._handle_status_command(cp_id)

            elif cmd == "session":
                if len(parts) < 2:
                    print("错误: 请指定会话ID")
                    print("用法: session <session_id>")
                else:
                    session_id = parts[1]
                    self._handle_session_command(session_id)

            elif cmd == "stats":
                self._handle_stats_command()

            else:
                print(f"未知命令: {cmd}")
                print("输入 'help' 查看可用命令")

        except Exception as e:
            self.logger.error(f"执行命令时出错: {e}")
            print(f"错误: {e}")

    def _handle_list_command(self, subcommand: str = None):
        """处理list命令"""
        if subcommand == "sessions":
            self._list_sessions()
        elif subcommand == "available":
            self._list_available_charging_points()
        elif subcommand == "active":
            self._list_active_charging_points()
        else:
            self._list_all_charging_points()

    def _list_all_charging_points(self):
        """列出所有充电桩"""
        try:
            charging_points = (
                self.central.message_dispatcher.charging_point_manager.get_all_charging_points()
            )

            if not charging_points:
                print("当前没有注册的充电桩")
                return

            print(
                f"\n{'充电桩ID':<20} {'位置':<30} {'状态':<15} {'价格(元/kWh)':<15} {'最大功率(kW)'}"
            )
            print("-" * 100)

            for cp in charging_points:
                cp_id = cp.get("cp_id", "N/A")
                location = cp.get("location", "N/A")
                status = cp.get("status", "N/A")
                price = cp.get("price_per_kwh", 0.0)

                print(
                    f"{cp_id:<20} {location:<30} {status:<15} {price:<15.4f}"
                )

            print(f"\n总计: {len(charging_points)} 个充电桩")

        except Exception as e:
            self.logger.error(f"获取充电桩列表失败: {e}")
            print(f"错误: 无法获取充电桩列表 - {e}")

    def _list_available_charging_points(self):
        """列出所有可用的充电桩"""
        try:
            charging_points = (
                self.central.message_dispatcher.charging_point_manager.get_available_charging_points()
            )

            if not charging_points:
                print("当前没有可用的充电桩")
                return

            print(
                f"\n{'充电桩ID':<20} {'位置':<30} {'价格(元/kWh)':<15} {'最大功率(kW)'}"
            )
            print("-" * 85)

            for cp in charging_points:
                cp_id = cp.get("cp_id", "N/A")
                location = cp.get("location", "N/A")
                price = cp.get("price_per_kwh", 0.0)

                print(f"{cp_id:<20} {location:<30} {price:<15.4f}")

            print(f"\n总计: {len(charging_points)} 个可用充电桩")

        except Exception as e:
            self.logger.error(f"获取可用充电桩列表失败: {e}")
            print(f"错误: 无法获取可用充电桩列表 - {e}")

    def _list_active_charging_points(self):
        """列出所有活跃状态的充电桩"""
        try:
            all_cps = (
                self.central.message_dispatcher.charging_point_manager.get_all_charging_points()
            )
            active_cps = [cp for cp in all_cps if cp.get("status") == "ACTIVE"]

            if not active_cps:
                print("当前没有活跃状态的充电桩")
                return

            print(
                f"\n{'充电桩ID':<20} {'位置':<30} {'价格(元/kWh)':<15} {'最大功率(kW)'}"
            )
            print("-" * 85)

            for cp in active_cps:
                cp_id = cp.get("cp_id", "N/A")
                location = cp.get("location", "N/A")
                price = cp.get("price_per_kwh", 0.0)

                print(f"{cp_id:<20} {location:<30} {price:<15.4f} ")

            print(f"\n总计: {len(active_cps)} 个活跃充电桩")

        except Exception as e:
            self.logger.error(f"获取活跃充电桩列表失败: {e}")
            print(f"错误: 无法获取活跃充电桩列表 - {e}")

    def _list_sessions(self):
        """列出所有充电会话"""
        try:
            sessions = (
                self.central.message_dispatcher.charging_session_manager.get_all_sessions()
            )

            if not sessions:
                print("当前没有充电会话记录")
                return

            print(f"\n{'会话ID':<38} {'充电桩ID':<20} {'司机ID':<20} {'状态':<15}")
            print("-" * 100)

            for session in sessions:
                session_id = session.get("session_id", "N/A")
                cp_id = session.get("cp_id", "N/A")
                driver_id = session.get("driver_id", "N/A")
                status = session.get("status", "N/A")

                print(f"{session_id:<38} {cp_id:<20} {driver_id:<20} {status:<15}")

            print(f"\n总计: {len(sessions)} 个充电会话")

        except Exception as e:
            self.logger.error(f"获取充电会话列表失败: {e}")
            print(f"错误: 无法获取充电会话列表 - {e}")

    def _handle_stop_command(self, cp_id: str):
        """处理停止充电桩命令"""
        try:
            # 构造手动命令消息
            message = {
                "type": "manual_command",
                "message_id": str(uuid.uuid4()),
                "command": "stop",
                "cp_id": cp_id,
                "admin_id": "admin_cli",
                "timestamp": int(time.time()),
            }

            # 使用MessageDispatcher处理命令
            response = self.central.message_dispatcher._handle_manual_command(
                client_id="admin_cli", message=message
            )

            # 显示结果
            if response.get("status") == "success":
                if cp_id == "all":
                    print(f"✓ 成功停止所有充电桩")
                else:
                    print(f"✓ 成功停止充电桩: {cp_id}")

                # 显示详细信息
                if "message" in response:
                    print(f"  {response['message']}")
            else:
                print(f"✗ 操作失败: {response.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error(f"停止充电桩失败: {e}")
            print(f"错误: 无法停止充电桩 - {e}")

    def _handle_resume_command(self, cp_id: str):
        """处理恢复充电桩命令"""
        try:
            # 构造手动命令消息
            message = {
                "type": "manual_command",
                "message_id": str(uuid.uuid4()),
                "command": "resume",
                "cp_id": cp_id,
                "admin_id": "admin_cli",
                "timestamp": int(time.time()),
            }

            # 使用MessageDispatcher处理命令
            response = self.central.message_dispatcher._handle_manual_command(
                client_id="admin_cli", message=message
            )

            # 显示结果
            if response.get("status") == "success":
                if cp_id == "all":
                    print(f"✓ 成功恢复所有充电桩")
                else:
                    print(f"✓ 成功恢复充电桩: {cp_id}")

                # 显示详细信息
                if "message" in response:
                    print(f"  {response['message']}")
            else:
                print(f"✗ 操作失败: {response.get('message', '未知错误')}")

        except Exception as e:
            self.logger.error(f"恢复充电桩失败: {e}")
            print(f"错误: 无法恢复充电桩 - {e}")

    def _handle_status_command(self, cp_id: str):
        """处理查看充电桩状态命令"""
        try:
            cp_info = self.central.message_dispatcher.charging_point_manager.get_charging_point(
                cp_id
            )

            if not cp_info:
                print(f"错误: 找不到充电桩 {cp_id}")
                return

            print(f"\n充电桩详细信息:")
            print("-" * 60)
            print(f"  充电桩ID:       {cp_info.get('cp_id', 'N/A')}")
            print(f"  位置:           {cp_info.get('location', 'N/A')}")
            print(f"  状态:           {cp_info.get('status', 'N/A')}")
            print(f"  价格:           {cp_info.get('price_per_kwh', 0.0):.4f} 元/kWh")
           

            last_connection = cp_info.get("last_connection_time")
            if last_connection:
                print(f"  最后连接时间:   {last_connection}")
            else:
                print(f"  最后连接时间:   从未连接")

            print("-" * 60)

        except Exception as e:
            self.logger.error(f"获取充电桩状态失败: {e}")
            print(f"错误: 无法获取充电桩状态 - {e}")

    def _handle_session_command(self, session_id: str):
        """处理查看充电会话命令"""
        try:
            session_info = (
                self.central.message_dispatcher.charging_session_manager.get_session(
                    session_id
                )
            )

            if not session_info:
                print(f"错误: 找不到充电会话 {session_id}")
                return

            print(f"\n充电会话详细信息:")
            print("-" * 60)
            print(f"  会话ID:         {session_info.get('session_id', 'N/A')}")
            print(f"  充电桩ID:       {session_info.get('cp_id', 'N/A')}")
            print(f"  司机ID:         {session_info.get('driver_id', 'N/A')}")
            print(f"  状态:           {session_info.get('status', 'N/A')}")
            print(f"  开始时间:       {session_info.get('start_time', 'N/A')}")

            end_time = session_info.get("end_time")
            if end_time:
                print(f"  结束时间:       {end_time}")

            energy = session_info.get("energy_consumed_kwh", 0.0)
            cost = session_info.get("total_cost", 0.0)
            print(f"  消耗电量:       {energy:.2f} kWh")
            print(f"  总费用:         {cost:.2f} 元")
            print("-" * 60)

        except Exception as e:
            self.logger.error(f"获取充电会话信息失败: {e}")
            print(f"错误: 无法获取充电会话信息 - {e}")

    def _handle_stats_command(self):
        """处理显示统计信息命令"""
        try:
            all_cps = (
                self.central.message_dispatcher.charging_point_manager.get_all_charging_points()
            )
            all_sessions = (
                self.central.message_dispatcher.charging_session_manager.get_all_sessions()
            )

            # 统计充电桩状态
            status_count = {}
            for cp in all_cps:
                status = cp.get("status", "UNKNOWN")
                status_count[status] = status_count.get(status, 0) + 1

            # 统计会话状态
            session_status_count = {}
            total_energy = 0.0
            total_cost = 0.0
            for session in all_sessions:
                status = session.get("status", "UNKNOWN")
                session_status_count[status] = session_status_count.get(status, 0) + 1

                energy = session.get("energy_consumed_kwh", 0.0)
                cost = session.get("total_cost", 0.0)
                if energy:
                    total_energy += energy
                if cost:
                    total_cost += cost

            print("\n系统统计信息:")
            print("=" * 60)

            print(f"\n充电桩统计:")
            print(f"  总数:           {len(all_cps)}")
            for status, count in status_count.items():
                print(f"  {status:<15} {count}")

            print(f"\n充电会话统计:")
            print(f"  总会话数:       {len(all_sessions)}")
            for status, count in session_status_count.items():
                print(f"  {status:<15} {count}")

            print(f"\n总体统计:")
            print(f"  总消耗电量:     {total_energy:.2f} kWh")
            print(f"  总收入:         {total_cost:.2f} 元")

            print("=" * 60)

        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")
            print(f"错误: 无法获取统计信息 - {e}")
