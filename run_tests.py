#!/usr/bin/env python3
"""
测试运行脚本
运行所有测试用例
"""

import subprocess
import sys
import os
import time

def run_test(test_name, test_file):
    """运行单个测试"""
    print(f"\n🧪 Running {test_name}...")
    print("=" * 50)
    
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        if result.returncode == 0:
            print(f"✅ {test_name} PASSED")
            return True
        else:
            print(f"❌ {test_name} FAILED")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {test_name} TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ {test_name} ERROR: {e}")
        return False

def main():
    """主函数"""
    print("🚀 EV Charging System Test Suite")
    print("=" * 50)
    
    # 测试列表
    tests = [
        ("Basic Functionality Test", "Test/test_basic_functionality.py"),
        ("Fault Handling Test", "Test/test_fault_handling.py"),
    ]
    
    results = {}
    
    # 运行所有测试
    for test_name, test_file in tests:
        if os.path.exists(test_file):
            results[test_name] = run_test(test_name, test_file)
            time.sleep(2)  # 测试间隔
        else:
            print(f"⚠️  Test file not found: {test_file}")
            results[test_name] = False
    
    # 打印测试结果
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print("=" * 50)
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("💥 Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
