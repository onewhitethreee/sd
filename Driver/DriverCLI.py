"""
Driver交互式命令行界面
用于充电司机的操作命令
"""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Driver.EV_Driver import Driver


class DriverCLI:
    """Driver命令行接口"""

    def __init__(self, driver: "Driver"):
        """
        初始化Driver CLI

        Args:
            driver: Driver实例
        """
        self.driver = driver
        self.running = False
        self.cli_thread = None
        self.logger = driver.logger

    def start(self):
        """启动交互式命令行界面"""
        if self.running:
            self.logger.warning("Driver CLI已经在运行中")
            return

        self.running = True
        self.cli_thread = threading.Thread(target=self._run_cli, daemon=True)
        self.cli_thread.start()
        self.logger.info("Driver CLI已启动")

    def stop(self):
        """停止交互式命令行界面"""
        if not self.running:
            # 已经停止，避免重复日志
            return

        self.running = False
        if self.cli_thread:
            self.cli_thread.join(timeout=2)
        self.logger.info("Driver CLI已停止")

    def _run_cli(self):
        """运行交互式命令循环"""
        self._print_help()

        while self.running and self.driver.running:
            try:
                command = input("\nDriver> ").strip()
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
  list                    - 显示可用的充电桩
  charge <cp_id>          - 在指定充电桩发起充电请求
  stop                    - 停止当前充电会话
  status                  - 显示当前充电状态
  history                 - 显示充电历史记录
  help                    - 显示此帮助信息
  quit                    - 退出应用程序
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
                print("退出Driver应用...")
                self.driver.running = False
                self.running = False

            elif cmd == "list":
                self._handle_list_command()

            elif cmd == "charge":
                if len(parts) < 2:
                    print("错误: 请指定充电桩ID")
                    print("用法: charge <cp_id>")
                else:
                    cp_id = parts[1]
                    self._handle_charge_command(cp_id)

            elif cmd == "stop":
                self._handle_stop_command()

            elif cmd == "status":
                self._handle_status_command()

            elif cmd == "history":
                self._handle_history_command()

            else:
                print(f"未知命令: {cmd}")
                print("输入 'help' 查看可用命令")

        except Exception as e:
            self.logger.error(f"执行命令时出错: {e}")
            print(f"错误: {e}")

    def _handle_list_command(self):
        """处理list命令 - 请求可用充电桩列表"""
        try:
            self.driver._request_available_cps()
            # 显示可用充电桩
            with self.driver.lock:
                if self.driver.available_charging_points:
                    print(f"\n可用充电桩列表:")
                    print("-" * 80)
                    self.driver._formatter_charging_points(
                        self.driver.available_charging_points
                    )
                else:
                    print("当前没有可用的充电桩")

        except Exception as e:
            self.logger.error(f"获取充电桩列表失败: {e}")
            print(f"错误: 无法获取充电桩列表 - {e}")

    def _handle_charge_command(self, cp_id: str):
        """处理charge命令 - 发起充电请求"""
        try:
            # 检查是否已经在充电
            with self.driver.lock:
                if self.driver.current_charging_session:
                    session = self.driver.current_charging_session
                    print(f"错误: 已有活跃的充电会话")
                    print(f"  会话ID: {session.get('session_id')}")
                    print(f"  充电桩: {session.get('cp_id')}")
                    print(f"请先停止当前充电会话")
                    return

            # 检查充电桩是否在可用列表中
            with self.driver.lock:
                available_ids = [
                    cp.get("id") for cp in self.driver.available_charging_points
                ]
                if cp_id not in available_ids:
                    print(f"警告: 充电桩 {cp_id} 可能不在可用列表中")
                    confirm = input("是否继续? (y/n): ").strip().lower()
                    if confirm != "y":
                        print("已取消充电请求")
                        return

            # 发送充电请求
            print(f"正在向充电桩 {cp_id} 发送充电请求...")
            success = self.driver._send_charge_request(cp_id)

            if success:
                print(f"✓ 充电请求已发送")
                print("等待Central系统响应...")
            else:
                print(f"✗ 充电请求发送失败")

        except Exception as e:
            self.logger.error(f"发送充电请求失败: {e}")
            print(f"错误: 无法发送充电请求 - {e}")

    def _handle_stop_command(self):
        """处理stop命令 - 停止充电"""
        try:
            with self.driver.lock:
                if not self.driver.current_charging_session:
                    print("当前没有活跃的充电会话")
                    return

                session = self.driver.current_charging_session
                print(f"正在停止充电会话...")
                print(f"  会话ID: {session.get('session_id')}")
                print(f"  充电桩: {session.get('cp_id')}")

            # 发送停止请求
            success = self.driver._send_stop_charging_request()

            if success:
                print(f"✓ 停止充电请求已发送")
                print("等待充电会话结束...")
            else:
                print(f"✗ 停止充电请求发送失败")

        except Exception as e:
            self.logger.error(f"停止充电失败: {e}")
            print(f"错误: 无法停止充电 - {e}")

    def _handle_status_command(self):
        """处理status命令 - 显示当前充电状态"""
        try:
            with self.driver.lock:
                if not self.driver.current_charging_session:
                    print("\n当前充电状态: 空闲")
                    print("没有活跃的充电会话")
                    return

                session = self.driver.current_charging_session

                print("\n当前充电状态:")
                print("=" * 60)
                print(f"  会话ID:         {session.get('session_id', 'N/A')}")
                print(f"  充电桩ID:       {session.get('cp_id', 'N/A')}")
                print(f"  状态:           充电中")
                print(
                    f"  已消耗电量:     {session.get('energy_consumed_kwh', 0.0):.3f} kWh"
                )
                print(f"  当前费用:       {session.get('total_cost', 0.0):.2f} 元")
                print(f"  充电速率:       {session.get('charging_rate', 0.0):.2f} kW")

                # 计算充电时长（如果有开始时间）
                if "start_time" in session:
                    import time

                    elapsed = time.time() - session.get("start_time", time.time())
                    minutes = int(elapsed // 60)
                    seconds = int(elapsed % 60)
                    print(f"  充电时长:       {minutes}分{seconds}秒")

                print("=" * 60)

        except Exception as e:
            self.logger.error(f"获取充电状态失败: {e}")
            print(f"错误: 无法获取充电状态 - {e}")

    def _handle_history_command(self):
        """处理history命令 - 显示充电历史"""
        try:
            with self.driver.lock:
                history = self.driver.charging_history

            if not history:
                print("\n没有充电历史记录")
                return

            print("\n充电历史记录:")
            print("=" * 80)

            for i, record in enumerate(history, 1):
                print(f"\n【{i}】 会话 {record.get('session_id', 'N/A')}")
                print(f"    ├─ 充电桩ID:     {record.get('cp_id', 'N/A')}")
                print(f"    ├─ 完成时间:     {record.get('completion_time', 'N/A')}")
                print(
                    f"    ├─ 消耗电量:     {record.get('energy_consumed_kwh', 0.0):.3f} kWh"
                )
                print(f"    ├─ 总费用:       {record.get('total_cost', 0.0):.2f} 元")

                # 如果有持续时间信息
                if "duration" in record:
                    print(f"    └─ 充电时长:     {record.get('duration')}")

            print("\n" + "=" * 80)
            print(f"总计: {len(history)} 条充电记录")

            # 计算总计
            total_energy = sum(r.get("energy_consumed_kwh", 0.0) for r in history)
            total_cost = sum(r.get("total_cost", 0.0) for r in history)
            print(f"总消耗电量: {total_energy:.3f} kWh")
            print(f"总费用: {total_cost:.2f} 元")
            print("=" * 80)

        except Exception as e:
            self.logger.error(f"获取充电历史失败: {e}")
            print(f"错误: 无法获取充电历史 - {e}")
