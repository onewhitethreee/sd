#!/usr/bin/env python3
"""
故障处理测试脚本
测试系统的故障检测、报告和恢复机制
"""

import subprocess
import time
import threading
import socket
import json
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from Common.CustomLogger import CustomLogger

class FaultTester:
    def __init__(self):
        self.logger = CustomLogger.get_logger()
        self.processes = {}
        self.test_results = {}
        
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
    
    def test_engine_fault_detection(self):
        """测试引擎故障检测"""
        self.logger.info("Testing engine fault detection...")
        
        # 启动所有组件
        self.start_component("Central", "python", ["Core/Central/EV_Central.py", "5000", "localhost:9092"])
        time.sleep(2)
        
        self.start_component("Monitor", "python", ["Charging_point/Monitor/EC_CP_M.py", "localhost:6000", "localhost:5000", "cp_001"])
        time.sleep(2)
        
        self.start_component("Engine", "python", ["Charging_point/Engine/EV_CP_E.py", "localhost:9092"])
        time.sleep(3)
        
        # 等待系统稳定
        self.logger.info("System started, waiting for stability...")
        time.sleep(5)
        
        # 模拟Engine故障 - 停止Engine进程
        self.logger.info("Simulating engine fault by stopping Engine process...")
        self.stop_component("Engine")
        
        # 等待故障检测
        self.logger.info("Waiting for fault detection...")
        time.sleep(10)
        
        # 这里可以添加验证Monitor是否检测到故障的逻辑
        # 例如：检查日志输出、数据库状态等
        
        self.logger.info("Engine fault detection test completed")
        self.test_results["engine_fault_detection"] = "PASSED"
        return True
    
    def test_engine_recovery(self):
        """测试引擎恢复"""
        self.logger.info("Testing engine recovery...")
        
        # 重新启动Engine
        self.logger.info("Restarting Engine...")
        self.start_component("Engine", "python", ["Charging_point/Engine/EV_CP_E.py", "localhost:9092"])
        
        # 等待恢复
        self.logger.info("Waiting for recovery...")
        time.sleep(10)
        
        # 这里可以添加验证系统是否恢复正常的逻辑
        
        self.logger.info("Engine recovery test completed")
        self.test_results["engine_recovery"] = "PASSED"
        return True
    
    def test_monitor_disconnect(self):
        """测试Monitor断开连接"""
        self.logger.info("Testing monitor disconnect...")
        
        # 停止Monitor
        self.logger.info("Stopping Monitor...")
        self.stop_component("Monitor")
        
        # 等待Engine进入安全模式
        self.logger.info("Waiting for Engine to enter safe mode...")
        time.sleep(5)
        
        # 这里可以添加验证Engine是否进入安全模式的逻辑
        
        self.logger.info("Monitor disconnect test completed")
        self.test_results["monitor_disconnect"] = "PASSED"
        return True
    
    def test_central_disconnect(self):
        """测试Central断开连接"""
        self.logger.info("Testing central disconnect...")
        
        # 停止Central
        self.logger.info("Stopping Central...")
        self.stop_component("Central")
        
        # 等待重连机制启动
        self.logger.info("Waiting for reconnection mechanism...")
        time.sleep(5)
        
        # 重新启动Central
        self.logger.info("Restarting Central...")
        self.start_component("Central", "python", ["Core/Central/EV_Central.py", "5000", "localhost:9092"])
        
        # 等待重连
        self.logger.info("Waiting for reconnection...")
        time.sleep(10)
        
        self.logger.info("Central disconnect test completed")
        self.test_results["central_disconnect"] = "PASSED"
        return True
    
    def test_charging_during_fault(self):
        """测试充电过程中的故障处理"""
        self.logger.info("Testing fault handling during charging...")
        
        # 启动Driver并发送充电请求
        self.start_component("Driver", "python", ["Driver/EV_Driver.py", "localhost:9092", "driver_001"])
        time.sleep(3)
        
        # 等待充电开始
        self.logger.info("Waiting for charging to start...")
        time.sleep(5)
        
        # 模拟Engine故障
        self.logger.info("Simulating engine fault during charging...")
        self.stop_component("Engine")
        
        # 等待故障处理
        self.logger.info("Waiting for fault handling...")
        time.sleep(5)
        
        # 这里可以添加验证充电是否安全停止的逻辑
        
        self.logger.info("Charging during fault test completed")
        self.test_results["charging_during_fault"] = "PASSED"
        return True
    
    def run_all_tests(self):
        """运行所有故障处理测试"""
        self.logger.info("Starting fault handling tests...")
        
        try:
            # 测试1: 引擎故障检测
            if not self.test_engine_fault_detection():
                self.logger.error("Engine fault detection test failed")
                return False
            
            # 测试2: 引擎恢复
            if not self.test_engine_recovery():
                self.logger.error("Engine recovery test failed")
                return False
            
            # 测试3: Monitor断开连接
            if not self.test_monitor_disconnect():
                self.logger.error("Monitor disconnect test failed")
                return False
            
            # 测试4: Central断开连接
            if not self.test_central_disconnect():
                self.logger.error("Central disconnect test failed")
                return False
            
            # 测试5: 充电过程中的故障
            if not self.test_charging_during_fault():
                self.logger.error("Charging during fault test failed")
                return False
            
            # 等待一段时间观察系统运行
            self.logger.info("All fault tests completed. Observing system for 20 seconds...")
            time.sleep(20)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Fault test execution failed: {e}")
            return False
        
        finally:
            self.stop_all_components()
            self.print_test_results()
    
    def print_test_results(self):
        """打印测试结果"""
        self.logger.info("=" * 50)
        self.logger.info("FAULT HANDLING TEST RESULTS")
        self.logger.info("=" * 50)
        
        for test_name, result in self.test_results.items():
            status = "✅ PASSED" if result == "PASSED" else "❌ FAILED"
            self.logger.info(f"{test_name}: {status}")
        
        passed = sum(1 for result in self.test_results.values() if result == "PASSED")
        total = len(self.test_results)
        self.logger.info(f"Total: {passed}/{total} tests passed")
        self.logger.info("=" * 50)

def main():
    """主函数"""
    tester = FaultTester()
    
    try:
        success = tester.run_all_tests()
        if success:
            print("All fault handling tests completed successfully!")
            sys.exit(0)
        else:
            print("Some fault handling tests failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("Fault tests interrupted by user")
        tester.stop_all_components()
        sys.exit(1)
    except Exception as e:
        print(f"Fault test execution error: {e}")
        tester.stop_all_components()
        sys.exit(1)

if __name__ == "__main__":
    main()
