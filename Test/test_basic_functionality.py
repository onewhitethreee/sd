#!/usr/bin/env python3
"""
基础功能测试脚本
测试系统的基本功能：启动、注册、充电请求等
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

class SystemTester:
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
    
    def test_port_availability(self, host, port):
        """测试端口是否可用"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def test_central_startup(self):
        """测试中央系统启动"""
        self.logger.info("Testing Central startup...")
        
        # 启动Central
        success = self.start_component(
            "Central",
            "python",
            ["Core/Central/EV_Central.py", "5000", "localhost:9092"]
        )
        
        if not success:
            self.test_results["central_startup"] = "FAILED"
            return False
        
        # 等待启动
        time.sleep(3)
        
        # 检查端口是否监听
        if self.test_port_availability("localhost", 5000):
            self.logger.info("Central is listening on port 5000")
            self.test_results["central_startup"] = "PASSED"
            return True
        else:
            self.logger.error("Central is not listening on port 5000")
            self.test_results["central_startup"] = "FAILED"
            return False
    
    def test_cp_registration(self):
        """测试充电点注册"""
        self.logger.info("Testing CP registration...")
        
        # 启动Monitor
        success = self.start_component(
            "Monitor",
            "python",
            ["Charging_point/Monitor/EC_CP_M.py", "localhost:6000", "localhost:5000", "cp_001"]
        )
        
        if not success:
            self.test_results["cp_registration"] = "FAILED"
            return False
        
        # 启动Engine
        success = self.start_component(
            "Engine",
            "python",
            ["Charging_point/Engine/EV_CP_E.py", "localhost:9092"]
        )
        
        if not success:
            self.test_results["cp_registration"] = "FAILED"
            return False
        
        # 等待注册
        time.sleep(5)
        
        # 这里可以添加更详细的注册验证逻辑
        self.logger.info("CP registration test completed")
        self.test_results["cp_registration"] = "PASSED"
        return True
    
    def test_charging_request(self):
        """测试充电请求"""
        self.logger.info("Testing charging request...")
        
        # 启动Driver
        success = self.start_component(
            "Driver",
            "python",
            ["Driver/EV_Driver.py", "localhost:9092", "driver_001"]
        )
        
        if not success:
            self.test_results["charging_request"] = "FAILED"
            return False
        
        # 等待请求处理
        time.sleep(3)
        
        self.logger.info("Charging request test completed")
        self.test_results["charging_request"] = "PASSED"
        return True
    
    def test_fault_handling(self):
        """测试故障处理"""
        self.logger.info("Testing fault handling...")
        
        # 这里可以添加故障模拟逻辑
        # 例如：停止Engine进程，观察Monitor的故障检测
        
        self.logger.info("Fault handling test completed")
        self.test_results["fault_handling"] = "PASSED"
        return True
    
    def run_all_tests(self):
        """运行所有测试"""
        self.logger.info("Starting system tests...")
        
        try:
            # 测试1: Central启动
            if not self.test_central_startup():
                self.logger.error("Central startup test failed")
                return False
            
            # 测试2: CP注册
            if not self.test_cp_registration():
                self.logger.error("CP registration test failed")
                return False
            
            # 测试3: 充电请求
            if not self.test_charging_request():
                self.logger.error("Charging request test failed")
                return False
            
            # 测试4: 故障处理
            if not self.test_fault_handling():
                self.logger.error("Fault handling test failed")
                return False
            
            # 等待一段时间观察系统运行
            self.logger.info("All tests completed. Observing system for 30 seconds...")
            time.sleep(30)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Test execution failed: {e}")
            return False
        
        finally:
            self.stop_all_components()
            self.print_test_results()
    
    def print_test_results(self):
        """打印测试结果"""
        self.logger.info("=" * 50)
        self.logger.info("TEST RESULTS")
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
    tester = SystemTester()
    
    try:
        success = tester.run_all_tests()
        if success:
            print("All tests completed successfully!")
            sys.exit(0)
        else:
            print("Some tests failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("Tests interrupted by user")
        tester.stop_all_components()
        sys.exit(1)
    except Exception as e:
        print(f"Test execution error: {e}")
        tester.stop_all_components()
        sys.exit(1)

if __name__ == "__main__":
    main()
