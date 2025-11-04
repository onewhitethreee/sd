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
        self.logger.info("Admin CLI ready. Press ENTER to show menu...")

        while self.running:
            try:
                # 等待用户输入
                user_input = input().strip()

                # 如果按 ENTER 不输入任何内容，显示菜单
                if not user_input:
                    self._show_menu()
                    continue

                self._process_command(user_input)

            except KeyboardInterrupt:
                print("\n检测到中断，使用 '0' 退出")
                continue
            except EOFError:
                break
            except Exception as e:
                self.logger.error(f"处理命令时出错: {e}")
                print(f"错误: {e}")

    def _show_menu(self):
        """显示菜单"""
        print("\n" + "=" * 60)
        print("  EV_CENTRAL - ADMIN CONTROL MENU")
        print("=" * 60)

        # 获取基本统计信息
        try:
            all_cps = self.central.message_dispatcher.charging_point_manager.get_all_charging_points()
            all_sessions = self.central.message_dispatcher.charging_session_manager.get_all_sessions()
            pending = self.central.message_dispatcher.get_pending_authorizations()

            print(f"  Total Charging Points: {len(all_cps)}")
            print(f"  Total Sessions: {len(all_sessions)}")
            print(f"  Pending Authorizations: {len(pending)}")
        except:
            pass

        print("-" * 60)
        print("  CHARGING POINT MANAGEMENT:")
        print("  [1] List all charging points")
        print("  [2] List available charging points")
        print("  [3] List active charging points")
        print("  [4] Show charging point status (requires CP ID)")
        print()
        print("  SESSION MANAGEMENT:")
        print("  [5] List all charging sessions")
        print("  [6] Show session details (requires Session ID)")
        print()
        print("  AUTHORIZATION:")
        print("  [7] List pending authorizations")
        print("  [8] Authorize charging point (requires CP ID or 'all')")
        print()
        print("  CONTROL:")
        print("  [9] Stop charging point (requires CP ID or 'all')")
        print("  [10] Resume charging point (requires CP ID or 'all')")
        print()
        print("  SYSTEM:")
        print("  [11] Show system statistics")
        print()
        print("  [0] Exit Admin Console")
        print("=" * 60)

    def _process_command(self, command: str):
        """
        处理用户输入的命令

        Args:
            command: 用户输入的命令字符串（数字选项）
        """
        try:
            if command == "0":
                print("退出管理员控制台...")
                self.running = False

            elif command == "1":
                self._show_registered_charging_points(filter_type=None)

            elif command == "2":
                self._show_registered_charging_points(filter_type="available")

            elif command == "3":
                self._show_registered_charging_points(filter_type="active")

            elif command == "4":
                cp_id = input("请输入充电桩ID: ").strip()
                if cp_id :
                    self._handle_status_command(cp_id)
                else:
                    print("错误: 充电桩ID不能为空")

            elif command == "5":
                self._list_sessions()

            elif command == "6":
                session_id = input("请输入会话ID: ").strip()
                if session_id:
                    self._handle_session_command(session_id)
                else:
                    print("错误: 会话ID不能为空")

            elif command == "7":
                self._list_pending_authorizations()

            elif command == "8":
                cp_id = input("请输入充电桩ID (或按回车授权所有): ").strip()
                if not cp_id:
                    cp_id = "all"
                self._handle_authorize_command(cp_id)

            elif command == "9":
                cp_id = input("请输入充电桩ID (或按回车停止所有): ").strip()
                if not cp_id:
                    cp_id = "all"
                self._handle_stop_command(cp_id)

            elif command == "10":
                cp_id = input("请输入充电桩ID (或按回车恢复所有): ").strip()
                if not cp_id:
                    cp_id = "all"
                self._handle_resume_command(cp_id)

            elif command == "11":
                self._handle_stats_command()

            else:
                print(f"未知选项: {command}")
                print("按 ENTER 显示菜单")

        except Exception as e:
            self.logger.error(f"执行命令时出错: {e}")
            print(f"错误: {e}")


    def _show_registered_charging_points(self, filter_type: str = None):
        """
        统一显示充电桩列表的方法

        Args:
            filter_type: 过滤类型，可选值：None(所有), 'available'(可用), 'active'(活跃)
        """
        try:
            # 根据过滤类型获取充电桩列表
            if filter_type == "available":
                charging_points = (
                    self.central.message_dispatcher.charging_point_manager.get_available_charging_points()
                )
                list_title = "可用"
                empty_message = "当前没有可用的充电桩"
            elif filter_type == "active":
                all_cps = (
                    self.central.message_dispatcher.charging_point_manager.get_all_charging_points()
                )
                charging_points = [cp for cp in all_cps if cp.get("status") == "ACTIVE"]
                list_title = "活跃"
                empty_message = "当前没有活跃状态的充电桩"
            else:
                # 默认显示所有充电桩
                charging_points = (
                    self.central.message_dispatcher.charging_point_manager.get_all_charging_points()
                )
                list_title = ""
                empty_message = "当前没有注册的充电桩"

            # 检查是否为空
            if not charging_points:
                print(empty_message)
                return

            # 根据是否显示状态列决定表头格式
            show_status = (filter_type is None)

            if show_status:
                # 显示所有充电桩时包含状态列
                print(f"\n{'充电桩ID':<20} {'位置':<30} {'状态':<15} {'价格(元/kWh)':<15}")
                print("-" * 85)
            else:
                # 过滤后的列表不显示状态列
                print(f"\n{'充电桩ID':<20} {'位置':<30} {'价格(元/kWh)':<15}")
                print("-" * 70)

            # 打印充电桩信息
            for cp in charging_points:
                cp_id = cp.get("cp_id", "N/A")
                location = cp.get("location", "N/A")
                price = cp.get("price_per_kwh", 0.0)

                if show_status:
                    status = cp.get("status", "N/A")
                    print(f"{cp_id:<20} {location:<30} {status:<15} {price:<15.4f}")
                else:
                    print(f"{cp_id:<20} {location:<30} {price:<15.4f}")

            # 打印总计
            count_text = f"{list_title}充电桩" if list_title else "充电桩"
            print(f"\n总计: {len(charging_points)} 个{count_text}")

        except Exception as e:
            error_type = "充电桩列表" if not filter_type else f"{filter_type}充电桩列表"
            self.logger.error(f"获取{error_type}失败: {e}")
            print(f"错误: 无法获取{error_type} - {e}")

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

    def _handle_authorize_command(self, cp_id: str):
        """处理授权命令"""
        if not cp_id:
            print("错误: 请指定充电点ID或使用 'all'")
            print("用法: authorize <cp_id> 或 authorize all")
            return

        try:
            if cp_id.lower() == "all":
                # 授权所有待授权的充电点
                pending = self.central.message_dispatcher.get_pending_authorizations()
                if not pending:
                    print("没有待授权的充电点")
                    return

                authorized_count = 0
                for auth_info in pending:
                    cp_id_to_auth = auth_info["cp_id"]
                    if self.central.message_dispatcher.authorize_charging_point(cp_id_to_auth):
                        authorized_count += 1
                        print(f"✅ 已授权充电点: {cp_id_to_auth}")

                print(f"\n成功授权 {authorized_count} 个充电点")
            else:
                # 授权指定的充电点
                if self.central.message_dispatcher.authorize_charging_point(cp_id):
                    print(f"✅ 充电点 {cp_id} 已获得授权")
                else:
                    print(f"❌ 无法授权充电点 {cp_id}（可能不在待授权列表中）")

        except Exception as e:
            self.logger.error(f"授权充电点失败: {e}")
            print(f"错误: 无法授权充电点 - {e}")

    def _list_pending_authorizations(self):
        """列出待授权的充电点"""
        try:
            pending = self.central.message_dispatcher.get_pending_authorizations()

            if not pending:
                print("当前没有待授权的充电点")
                return

            print("\n待授权的充电点:")
            print("=" * 60)
            for auth_info in pending:
                cp_id = auth_info["cp_id"]
                client_id = auth_info["client_id"]
                pending_time = auth_info["pending_time"]
                print(f"  充电点ID:       {cp_id}")
                print(f"  客户端ID:      {client_id}")
                print(f"  等待时间:      {pending_time:.1f} 秒")
                print(f"  操作:          使用 'authorize {cp_id}' 命令授权")
                print("-" * 60)

        except Exception as e:
            self.logger.error(f"获取待授权列表失败: {e}")
            print(f"错误: 无法获取待授权列表 - {e}")

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
