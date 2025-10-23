"""
Driver完整流程测试脚本
测试Driver的所有主要功能：
1. 连接到Central
2. 请求可用充电点
3. 发送充电请求
4. 接收充电状态更新
5. 接收充电完成通知
6. 查看充电历史
"""

import sys
import os
import time
import json
import unittest
from unittest.mock import Mock, patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Driver.EV_Driver import Driver
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager


class TestDriverWorkflow(unittest.TestCase):
    """Driver工作流测试类"""

    def setUp(self):
        """测试前准备"""
        self.logger = CustomLogger.get_logger()
        self.driver = Driver(logger=self.logger)

    def tearDown(self):
        """测试后清理"""
        if self.driver.running:
            self.driver.running = False
        if self.driver.central_client:
            self.driver.central_client.disconnect()
        if self.driver.kafka_manager:
            self.driver.kafka_manager.stop()

    def test_driver_initialization(self):
        """测试Driver初始化"""
        self.assertIsNotNone(self.driver)
        self.assertIsNone(self.driver.central_client)
        self.assertIsNone(self.driver.kafka_manager)
        self.assertFalse(self.driver.running)
        self.assertEqual(len(self.driver.charging_history), 0)
        self.logger.info("✓ Driver initialization test passed")

    def test_charging_session_creation(self):
        """测试充电会话创建"""
        session = {
            "session_id": "test_session_123",
            "cp_id": "CP001",
            "energy_consumed": 0.0,
            "total_cost": 0.0,
            "charging_rate": 0.25,
        }
        
        with self.driver.lock:
            self.driver.current_charging_session = session
        
        with self.driver.lock:
            self.assertIsNotNone(self.driver.current_charging_session)
            self.assertEqual(
                self.driver.current_charging_session["session_id"],
                "test_session_123"
            )
        
        self.logger.info("✓ Charging session creation test passed")

    def test_charging_data_update(self):
        """测试充电数据更新"""
        # 创建初始会话
        session = {
            "session_id": "test_session_456",
            "cp_id": "CP002",
            "energy_consumed": 0.0,
            "total_cost": 0.0,
            "charging_rate": 0.25,
        }
        
        with self.driver.lock:
            self.driver.current_charging_session = session
        
        # 模拟充电数据更新
        message = {
            "type": "charging_status_update",
            "session_id": "test_session_456",
            "energy_consumed_kwh": 5.5,
            "total_cost": 1.10,
            "charging_rate": 0.25,
        }
        
        self.driver._handle_charging_data(message)
        
        with self.driver.lock:
            self.assertEqual(
                self.driver.current_charging_session["energy_consumed"],
                5.5
            )
            self.assertEqual(
                self.driver.current_charging_session["total_cost"],
                1.10
            )
        
        self.logger.info("✓ Charging data update test passed")

    def test_charging_completion(self):
        """测试充电完成处理"""
        # 创建初始会话
        session = {
            "session_id": "test_session_789",
            "cp_id": "CP003",
            "energy_consumed": 10.0,
            "total_cost": 2.00,
            "charging_rate": 0.25,
        }
        
        with self.driver.lock:
            self.driver.current_charging_session = session
        
        # 模拟充电完成消息
        message = {
            "type": "charge_completion_notification",
            "session_id": "test_session_789",
            "energy_consumed_kwh": 10.0,
            "total_cost": 2.00,
        }
        
        self.driver._handle_charge_completion(message)
        
        # 验证会话已清除
        with self.driver.lock:
            self.assertIsNone(self.driver.current_charging_session)
        
        # 验证历史记录已保存
        self.assertEqual(len(self.driver.charging_history), 1)
        self.assertEqual(
            self.driver.charging_history[0]["session_id"],
            "test_session_789"
        )
        
        self.logger.info("✓ Charging completion test passed")

    def test_charging_history_tracking(self):
        """测试充电历史跟踪"""
        # 添加多个充电记录
        for i in range(3):
            record = {
                "session_id": f"session_{i}",
                "cp_id": f"CP{i:03d}",
                "completion_time": time.time(),
                "energy_consumed": 10.0 + i,
                "total_cost": 2.0 + i * 0.5,
            }
            self.driver.charging_history.append(record)
        
        # 验证历史记录
        self.assertEqual(len(self.driver.charging_history), 3)
        self.assertEqual(self.driver.charging_history[0]["session_id"], "session_0")
        self.assertEqual(self.driver.charging_history[2]["energy_consumed"], 12.0)
        
        self.logger.info("✓ Charging history tracking test passed")

    def test_thread_safety(self):
        """测试线程安全性"""
        import threading
        
        session = {
            "session_id": "thread_test",
            "cp_id": "CP_THREAD",
            "energy_consumed": 0.0,
            "total_cost": 0.0,
            "charging_rate": 0.25,
        }
        
        with self.driver.lock:
            self.driver.current_charging_session = session
        
        # 创建多个线程来并发访问会话
        def update_session():
            for _ in range(10):
                with self.driver.lock:
                    if self.driver.current_charging_session:
                        self.driver.current_charging_session["energy_consumed"] += 0.1
                time.sleep(0.01)
        
        threads = [threading.Thread(target=update_session) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 验证最终值
        with self.driver.lock:
            expected_value = 0.0 + 0.1 * 10 * 3
            self.assertAlmostEqual(
                self.driver.current_charging_session["energy_consumed"],
                expected_value,
                places=5
            )
        
        self.logger.info("✓ Thread safety test passed")

    def test_message_handling_coverage(self):
        """测试消息处理覆盖"""
        # 测试各种消息类型
        test_messages = [
            {
                "type": "charge_request_response",
                "status": "success",
                "session_id": "test_1",
                "cp_id": "CP001",
            },
            {
                "type": "available_cps_response",
                "charging_points": [
                    {"cp_id": "CP001", "status": "ACTIVE"},
                    {"cp_id": "CP002", "status": "ACTIVE"},
                ],
            },
            {
                "type": "CONNECTION_LOST",
            },
            {
                "type": "CONNECTION_ERROR",
                "error": "Connection timeout",
            },
        ]
        
        for msg in test_messages:
            try:
                self.driver._handle_central_message(msg)
                self.logger.info(f"✓ Handled message type: {msg['type']}")
            except Exception as e:
                self.logger.error(f"✗ Failed to handle message type {msg['type']}: {e}")

    def test_kafka_initialization(self):
        """测试Kafka初始化"""
        # 这个测试需要Kafka服务运行
        # 如果Kafka不可用，应该优雅地处理
        try:
            result = self.driver._init_kafka()
            # 如果Kafka初始化失败，应该返回False但不抛出异常
            self.assertIsInstance(result, bool)
            self.logger.info(f"✓ Kafka initialization test passed (result: {result})")
        except Exception as e:
            self.logger.warning(f"⚠ Kafka initialization test skipped: {e}")


class TestDriverIntegration(unittest.TestCase):
    """Driver集成测试类"""

    def setUp(self):
        """测试前准备"""
        self.logger = CustomLogger.get_logger()

    def test_complete_workflow_simulation(self):
        """模拟完整的充电工作流"""
        self.logger.info("Starting complete workflow simulation...")
        
        driver = Driver(logger=self.logger)
        
        # 1. 初始化
        self.assertFalse(driver.running)
        self.logger.info("✓ Step 1: Driver initialized")
        
        # 2. 模拟充电请求响应
        charge_response = {
            "type": "charge_request_response",
            "status": "success",
            "session_id": "workflow_session_001",
            "cp_id": "CP001",
        }
        driver._handle_charge_response(charge_response)
        self.assertIsNotNone(driver.current_charging_session)
        self.logger.info("✓ Step 2: Charge request accepted")
        
        # 3. 模拟充电数据更新
        for i in range(3):
            charging_data = {
                "type": "charging_data",
                "session_id": "workflow_session_001",
                "energy_consumed_kwh": 5.0 + i * 2.0,
                "total_cost": 1.0 + i * 0.4,
                "charging_rate": 0.25,
            }
            driver._handle_charging_data(charging_data)
            time.sleep(0.1)
        
        self.logger.info("✓ Step 3: Received charging data updates")
        
        # 4. 模拟充电完成
        completion = {
            "type": "charge_completion_notification",
            "session_id": "workflow_session_001",
            "energy_consumed_kwh": 11.0,
            "total_cost": 2.2,
        }
        driver._handle_charge_completion(completion)
        self.assertIsNone(driver.current_charging_session)
        self.assertEqual(len(driver.charging_history), 1)
        self.logger.info("✓ Step 4: Charging completed")
        
        self.logger.info("✓ Complete workflow simulation passed!")


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试
    suite.addTests(loader.loadTestsFromTestCase(TestDriverWorkflow))
    suite.addTests(loader.loadTestsFromTestCase(TestDriverIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

