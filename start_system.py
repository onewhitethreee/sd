#!/usr/bin/env python3
"""
系统快速启动脚本
自动启动所有系统组件
"""

import subprocess
import time
import sys
import os
import signal
import threading

class SystemStarter:
    def __init__(self):
        self.processes = {}
        self.running = True
        
    def start_component(self, name, command, args, delay=0):
        """启动系统组件"""
        try:
            if delay > 0:
                time.sleep(delay)
                
            full_command = [command] + args
            print(f"Starting {name}: {' '.join(full_command)}")
            
            process = subprocess.Popen(
                full_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.processes[name] = process
            print(f"✅ {name} started with PID: {process.pid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start {name}: {e}")
            return False
    
    def stop_all_components(self):
        """停止所有组件"""
        print("\n🛑 Stopping all components...")
        for name, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"✅ {name} stopped")
            except Exception as e:
                print(f"❌ Error stopping {name}: {e}")
        self.processes.clear()
    
    def signal_handler(self, signum, frame):
        """信号处理器"""
        print(f"\n🛑 Received signal {signum}, shutting down...")
        self.running = False
        self.stop_all_components()
        sys.exit(0)
    
    def monitor_processes(self):
        """监控进程状态"""
        while self.running:
            for name, process in list(self.processes.items()):
                if process.poll() is not None:
                    print(f"⚠️  {name} process terminated unexpectedly")
                    del self.processes[name]
            time.sleep(1)
    
    def start_system(self):
        """启动整个系统"""
        print("🚀 Starting EV Charging System...")
        print("=" * 50)
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # 启动组件
        components = [
            ("Central", "python", ["Core/Central/EV_Central.py", "5000", "localhost:9092"], 0),
            ("Monitor", "python", ["Charging_point/Monitor/EC_CP_M.py", "localhost:6000", "localhost:5000", "cp_001"], 3),
            ("Engine", "python", ["Charging_point/Engine/EV_CP_E.py", "localhost:9092"], 2),
            ("Driver", "python", ["Driver/EV_Driver.py", "localhost:9092", "driver_001"], 5),
        ]
        
        # 启动所有组件
        for name, command, args, delay in components:
            if not self.start_component(name, command, args, delay):
                print(f"❌ Failed to start {name}, stopping system...")
                self.stop_all_components()
                return False
        
        print("\n✅ All components started successfully!")
        print("=" * 50)
        print("System is running. Press Ctrl+C to stop all components.")
        print("=" * 50)
        
        # 启动监控线程
        monitor_thread = threading.Thread(target=self.monitor_processes, daemon=True)
        monitor_thread.start()
        
        # 保持运行
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
        return True

def main():
    """主函数"""
    starter = SystemStarter()
    
    try:
        success = starter.start_system()
        if success:
            print("System started successfully!")
        else:
            print("Failed to start system!")
            sys.exit(1)
    except Exception as e:
        print(f"Error starting system: {e}")
        starter.stop_all_components()
        sys.exit(1)

if __name__ == "__main__":
    main()
