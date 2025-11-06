import threading
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Core.Central.EV_Central import EV_Central


class AdminCLI:
    """Administrator Command Line Interface"""

    def __init__(self, central: "EV_Central"):
        """
        Initialize Admin CLI

        Args:
            central: EV_Central instance
        """
        self.central = central
        self.running = False
        self.cli_thread = None
        self.logger = central.logger

    def start(self):
        """启动交互式命令行界面"""
        if self.running:
            self.logger.warning("Admin CLI is already running")
            return

        self.running = True
        self.cli_thread = threading.Thread(target=self._run_cli, daemon=True)
        self.cli_thread.start()
        self.logger.info("Admin CLI has started")

    def stop(self):
        """Stop interactive command line interface"""
        self.running = False
        if self.cli_thread:
            self.cli_thread.join(timeout=2)
        self.logger.info("Admin CLI has stopped")

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
                print("\nInterrupt detected, use '0' to exit")
                continue
            except EOFError:
                break
            except Exception as e:
                self.logger.error(f"Error processing command: {e}")

    def _show_menu(self):
        """显示菜单"""
        print("\n" + "=" * 60)
        print("  EV_CENTRAL - ADMIN CONTROL MENU")
        print("=" * 60)

        # 获取基本统计信息
        try:
            all_cps = (
                self.central.message_dispatcher.charging_point_manager.get_all_charging_points()
            )
            all_sessions = (
                self.central.message_dispatcher.charging_session_manager.get_all_sessions()
            )
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
        Process user input commands

        Args:
            command: User input command string (numeric option)
        """
        try:
            if command == "0":
                print("Exiting admin console...")
                self.running = False

            elif command == "1":
                self._show_registered_charging_points(filter_type=None)

            elif command == "2":
                self._show_registered_charging_points(filter_type="available")

            elif command == "3":
                self._show_registered_charging_points(filter_type="active")

            elif command == "4":
                cp_id = input("Please enter Charging Point ID: ").strip()
                if cp_id:
                    self._handle_status_command(cp_id)
                else:
                    print("Error: Charging Point ID cannot be empty")

            elif command == "5":
                self._list_sessions()

            elif command == "6":
                session_id = input("Please enter Session ID: ").strip()
                if session_id:
                    self._handle_session_command(session_id)
                else:
                    print("Error: Session ID cannot be empty")

            elif command == "7":
                self._list_pending_authorizations()

            elif command == "8":
                cp_id = input(
                    "Please enter Charging Point ID (or press Enter to authorize all): "
                ).strip()
                if not cp_id:
                    cp_id = "all"
                self._handle_authorize_command(cp_id)

            elif command == "9":
                cp_id = input(
                    "Please enter Charging Point ID (or press Enter to stop all): "
                ).strip()
                if not cp_id:
                    cp_id = "all"
                self._handle_stop_command(cp_id)

            elif command == "10":
                cp_id = input(
                    "Please enter Charging Point ID (or press Enter to resume all): "
                ).strip()
                if not cp_id:
                    cp_id = "all"
                self._handle_resume_command(cp_id)

            elif command == "11":
                self._handle_stats_command()

            else:
                print(f"Unknown option: {command}")
                print("Press ENTER to display menu")

        except Exception as e:
            self.logger.error(f"Error executing command: {e}")

    def _show_registered_charging_points(self, filter_type: str = None):
        """
        Unified method to display charging point list

        Args:
            filter_type: Filter type, possible values: None(all), 'available'(available), 'active'(active)
        """
        try:
            # Get charging point list based on filter type
            if filter_type == "available":
                charging_points = (
                    self.central.message_dispatcher.charging_point_manager.get_available_charging_points()
                )
                list_title = "Available"
                empty_message = "No available charging points currently"
            elif filter_type == "active":
                all_cps = (
                    self.central.message_dispatcher.charging_point_manager.get_all_charging_points()
                )
                charging_points = [cp for cp in all_cps if cp.get("status") == "ACTIVE"]
                list_title = "Active"
                empty_message = "No active charging points currently"
            else:
                charging_points = (
                    self.central.message_dispatcher.charging_point_manager.get_all_charging_points()
                )
                list_title = ""
                empty_message = "No registered charging points currently"

            # 检查是否为空
            if not charging_points:
                print(empty_message)
                return

            # Decide table header format based on whether to show status column
            show_status = filter_type is None

            if show_status:
                # Include status column when showing all charging points
                print(
                    f"\n{'CP ID':<20} {'Location':<30} {'Status':<15} {'Price(€/kWh)':<15}"
                )
                print("-" * 85)
            else:

                print(f"\n{'CP ID':<20} {'Location':<30} {'Price(€/kWh)':<15}")
                print("-" * 70)

            for cp in charging_points:
                cp_id = cp.get("cp_id", "N/A")
                location = cp.get("location", "N/A")
                price = cp.get("price_per_kwh", 0.0)

                if show_status:
                    status = cp.get("status", "N/A")
                    print(f"{cp_id:<20} {location:<30} {status:<15} {price:<15.4f}")
                else:
                    print(f"{cp_id:<20} {location:<30} {price:<15.4f}")

            # Print total
            count_text = (
                f"{list_title} Charging Points" if list_title else "Charging Points"
            )
            print(f"\nTotal: {len(charging_points)} {count_text}")

        except Exception as e:
            error_type = (
                "charging points list"
                if not filter_type
                else f"{filter_type} charging points list"
            )
            self.logger.error(f"Failed to get {error_type}: {e}")
            print(f"Error: Unable to get {error_type} - {e}")

    def _list_sessions(self):
        """List all charging sessions"""
        try:
            sessions = (
                self.central.message_dispatcher.charging_session_manager.get_all_sessions()
            )

            if not sessions:
                print("No charging session records currently")
                return

            print(
                f"\n{'Session ID':<38} {'CP ID':<20} {'Driver ID':<20} {'Status':<15}"
            )
            print("-" * 100)

            for session in sessions:
                session_id = session.get("session_id", "N/A")
                cp_id = session.get("cp_id", "N/A")
                driver_id = session.get("driver_id", "N/A")
                status = session.get("status", "N/A")

                print(f"{session_id:<38} {cp_id:<20} {driver_id:<20} {status:<15}")

            print(f"\nTotal: {len(sessions)} charging sessions")

        except Exception as e:
            self.logger.error(f"Failed to get charging sessions list: {e}")
            print(f"Error: Unable to get charging sessions list - {e}")

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

            if response.get("status") == "success":
                if cp_id == "all":
                    print(f"✓ Successfully stopped all charging points")
                else:
                    print(f"✓ Successfully stopped charging point: {cp_id}")

                if "message" in response:
                    print(f"  {response['message']}")
            else:
                print(f"✗ Operation failed: {response.get('message', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"Failed to stop charging point: {e}")

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

            if response.get("status") == "success":
                if cp_id == "all":
                    print(f"✓ Successfully resumed all charging points")
                else:
                    print(f"✓ Successfully resumed charging point: {cp_id}")

                if "message" in response:
                    print(f"  {response['message']}")
            else:
                print(f"✗ Operation failed: {response.get('message', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"Failed to resume charging point: {e}")
            print(f"Error: Unable to resume charging point - {e}")

    def _handle_status_command(self, cp_id: str):
        """处理查看充电桩状态命令"""
        try:
            cp_info = self.central.message_dispatcher.charging_point_manager.get_charging_point(
                cp_id
            )

            if not cp_info:
                print(f"Error: Cannot find charging point {cp_id}")
                return

            print(f"\nCharging Point Details:")
            print("-" * 60)
            print(f"  CP ID:          {cp_info.get('cp_id', 'N/A')}")
            print(f"  Location:       {cp_info.get('location', 'N/A')}")
            print(f"  Status:         {cp_info.get('status', 'N/A')}")
            print(f"  Price:          {cp_info.get('price_per_kwh', 0.0):.4f} €/kWh")

            last_connection = cp_info.get("last_connection_time")
            if last_connection:
                print(f"  Last Connection: {last_connection}")
            else:
                print(f"  Last Connection: Never connected")

            print("-" * 60)

        except Exception as e:
            self.logger.error(f"Failed to get charging point status: {e}")

    def _handle_session_command(self, session_id: str):
        """处理查看充电会话命令"""
        try:
            session_info = (
                self.central.message_dispatcher.charging_session_manager.get_session(
                    session_id
                )
            )

            if not session_info:
                print(f"Error: Cannot find charging session {session_id}")
                return

            print(f"\nCharging Session Details:")
            print("-" * 60)
            print(f"  Session ID:     {session_info.get('session_id', 'N/A')}")
            print(f"  CP ID:          {session_info.get('cp_id', 'N/A')}")
            print(f"  Driver ID:      {session_info.get('driver_id', 'N/A')}")
            print(f"  Status:         {session_info.get('status', 'N/A')}")
            print(f"  Start Time:     {session_info.get('start_time', 'N/A')}")

            end_time = session_info.get("end_time")
            if end_time:
                print(f"  End Time:       {end_time}")

            energy = session_info.get("energy_consumed_kwh", 0.0)
            cost = session_info.get("total_cost", 0.0)
            print(f"  Energy Used:    {energy:.2f} kWh")
            print(f"  Total Cost:     {cost:.2f} €")
            print("-" * 60)

        except Exception as e:
            self.logger.error(f"Failed to get charging session information: {e}")
            print(f"Error: Unable to get charging session information - {e}")

    def _handle_authorize_command(self, cp_id: str):
        """Handle authorization command"""
        if not cp_id:
            print("Error: Please specify charging point ID or use 'all'")
            print("Usage: authorize <cp_id> or authorize all")
            return

        try:
            if cp_id.lower() == "all":
                # Authorize all pending charging points
                pending = self.central.message_dispatcher.get_pending_authorizations()
                if not pending:
                    print("No pending charging points to authorize")
                    return

                authorized_count = 0
                for auth_info in pending:
                    cp_id_to_auth = auth_info["cp_id"]
                    if self.central.message_dispatcher.authorize_charging_point(
                        cp_id_to_auth
                    ):
                        authorized_count += 1
                        print(f"✓  Authorized charging point: {cp_id_to_auth}")

                print(f"\nSuccessfully authorized {authorized_count} charging points")
            else:
                # Authorize specified charging point
                if self.central.message_dispatcher.authorize_charging_point(cp_id):
                    print(f"✓  Charging point {cp_id} has been authorized")
                else:
                    print(
                        f"✗  Unable to authorize charging point {cp_id} (may not be in pending list)"
                    )

        except Exception as e:
            self.logger.error(f"Failed to authorize charging point: {e}")
            print(f"Error: Unable to authorize charging point - {e}")

    def _list_pending_authorizations(self):
        """List pending charging points for authorization"""
        try:
            pending = self.central.message_dispatcher.get_pending_authorizations()

            if not pending:
                print("No pending charging points for authorization currently")
                return

            print("\nPending Charging Points for Authorization:")
            print("=" * 60)
            for auth_info in pending:
                cp_id = auth_info["cp_id"]
                client_id = auth_info["client_id"]
                pending_time = auth_info["pending_time"]
                print(f"  CP ID:          {cp_id}")
                print(f"  Client ID:      {client_id}")
                print(f"  Waiting Time:   {pending_time:.1f} seconds")
                print(f"  Action:         Use 'authorize {cp_id}' command to authorize")
                print("-" * 60)

        except Exception as e:
            self.logger.error(f"Failed to get pending authorizations list: {e}")
            print(f"Error: Unable to get pending authorizations list - {e}")

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

            print("\nSystem Statistics:")
            print("=" * 60)

            print(f"\nCharging Points Statistics:")
            print(f"  Total:          {len(all_cps)}")
            for status, count in status_count.items():
                print(f"  {status:<15} {count}")

            print(f"\nCharging Sessions Statistics:")
            print(f"  Total Sessions: {len(all_sessions)}")
            for status, count in session_status_count.items():
                print(f"  {status:<15} {count}")

            print(f"\nOverall Statistics:")
            print(f"  Total Energy:   {total_energy:.2f} kWh")
            print(f"  Total Revenue:  {total_cost:.2f} €")

            print("=" * 60)

        except Exception as e:
            self.logger.error(f"Failed to get statistics: {e}")
            print(f"Error: Unable to get statistics - {e}")
