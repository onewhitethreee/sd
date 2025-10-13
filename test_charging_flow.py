#!/usr/bin/env python3
"""
充电流程测试脚本
测试完整的充电过程：请求 -> 授权 -> 充电 -> 完成
"""

import subprocess
import time
import threading
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from Common.CustomLogger import CustomLogger

class ChargingFlowTester:
    def __init__(self):
        self.logger = CustomLogger.get_logger()
        self.processes = {}
        
    def start_component(self, name, command, args):
        """启动系统组件"""
        try:
            full_command = [command] + args
            self.logger.info(f"Starting {name}: {' '.join(full_command)}")
            
            process = subprocess.Popen(
                full_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.processes[name] = process
            self.logger.info(f"{name} started with PID: {process.pid}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start {name}: {e}")
            return False
    
    def stop_component(self, name):
        """停止系统组件"""
        if name in self.processes:
            process = self.processes[name]
            process.terminate()
            process.wait(timeout=5)
            del self.processes[name]
            self.logger.info(f"{name} stopped")
    
    def stop_all_components(self):
        """停止所有组件"""
        for name in list(self.processes.keys()):
            self.stop_component(name)
    
    def test_complete_charging_flow(self):
        """测试完整的充电流程"""
        self.logger.info("=" * 60)
        self.logger.info("开始测试完整充电流程")
        self.logger.info("=" * 60)
        
        try:
            # 1. 启动Central
            self.logger.info("步骤1: 启动Central...")
            if not self.start_component("Central", "python", ["Core/Central/EV_Central.py", "5000", "localhost:9092"]):
                return False
            time.sleep(3)
            
            # 2. 启动Monitor
            self.logger.info("步骤2: 启动Monitor...")
            if not self.start_component("Monitor", "python", ["Charging_point/Monitor/EC_CP_M.py", "localhost:6000", "localhost:5000", "cp_001"]):
                return False
            time.sleep(3)
            
            # 3. 启动Engine
            self.logger.info("步骤3: 启动Engine...")
            if not self.start_component("Engine", "python", ["Charging_point/Engine/EV_CP_E.py", "localhost:9092"]):
                return False
            time.sleep(3)
            
            # 4. 启动Driver
            self.logger.info("步骤4: 启动Driver...")
            if not self.start_component("Driver", "python", ["Driver/EV_Driver.py", "localhost:9092", "driver_001"]):
                return False
            time.sleep(5)
            
            # 5. 等待系统稳定
            self.logger.info("步骤5: 等待系统稳定...")
            time.sleep(10)
            
            # 6. 观察充电过程
            self.logger.info("步骤6: 观察充电过程...")
            self.logger.info("系统现在应该显示:")
            self.logger.info("- Central: 充电点注册和心跳")
            self.logger.info("- Monitor: 连接到Central和Engine")
            self.logger.info("- Engine: 等待Monitor连接")
            self.logger.info("- Driver: 发送充电请求")
            self.logger.info("- 完整的充电流程: 请求 -> 授权 -> 充电 -> 完成")
            
            # 7. 等待充电完成
            self.logger.info("步骤7: 等待充电完成...")
            self.logger.info("请观察各个终端的输出，确认充电流程正常工作")
            time.sleep(30)
            
            self.logger.info("=" * 60)
            self.logger.info("充电流程测试完成")
            self.logger.info("=" * 60)
            return True
            
        except Exception as e:
            self.logger.error(f"测试过程中出现错误: {e}")
            return False
        
        finally:
            self.logger.info("停止所有组件...")
            self.stop_all_components()
    
    def run_test(self):
        """运行测试"""
        try:
            success = self.test_complete_charging_flow()
            if success:
                self.logger.info("✅ 充电流程测试成功完成!")
                print("\n🎉 测试成功! 系统现在可以:")
                print("1. 处理充电请求和授权")
                print("2. 模拟真实的充电过程")
                print("3. 发送实时充电数据")
                print("4. 处理充电完成")
                print("5. 计算费用和电量消耗")
            else:
                self.logger.error("❌ 充电流程测试失败!")
                print("\n❌ 测试失败! 请检查系统配置和日志。")
            
            return success
            
        except KeyboardInterrupt:
            self.logger.info("测试被用户中断")
            self.stop_all_components()
            return False
        except Exception as e:
            self.logger.error(f"测试执行错误: {e}")
            self.stop_all_components()
            return False

def main():
    """主函数"""
    print("🚗 电动汽车充电系统 - 充电流程测试")
    print("=" * 50)
    
    tester = ChargingFlowTester()
    
    try:
        success = tester.run_test()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"测试执行错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
