"""
Driver简单功能测试脚本
验证Driver的基本功能是否正常工作
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Driver.EV_Driver import Driver
from Common.CustomLogger import CustomLogger


def test_driver_basic_functionality():
    """测试Driver的基本功能"""
    logger = CustomLogger.get_logger()
    logger.info("=" * 60)
    logger.info("Starting Driver Basic Functionality Tests")
    logger.info("=" * 60)
    
    # 测试1: Driver初始化
    logger.info("\n[Test 1] Driver Initialization")
    try:
        driver = Driver(logger=logger)
        assert driver is not None
        assert driver.central_client is None
        assert driver.kafka_manager is None
        assert driver.running is False
        assert len(driver.charging_history) == 0
        logger.info("✓ PASS: Driver initialized successfully")
    except Exception as e:
        logger.error(f"✗ FAIL: Driver initialization failed: {e}")
        return False
    
    # 测试2: 充电会话创建
    logger.info("\n[Test 2] Charging Session Creation")
    try:
        session = {
            "session_id": "test_session_001",
            "cp_id": "CP001",
            "energy_consumed": 0.0,
            "total_cost": 0.0,
            "charging_rate": 0.25,
        }
        
        with driver.lock:
            driver.current_charging_session = session
        
        with driver.lock:
            assert driver.current_charging_session is not None
            assert driver.current_charging_session["session_id"] == "test_session_001"
        
        logger.info("✓ PASS: Charging session created successfully")
    except Exception as e:
        logger.error(f"✗ FAIL: Charging session creation failed: {e}")
        return False
    
    # 测试3: 充电数据更新
    logger.info("\n[Test 3] Charging Data Update")
    try:
        message = {
            "type": "charging_status_update",
            "session_id": "test_session_001",
            "energy_consumed_kwh": 5.5,
            "total_cost": 1.10,
            "charging_rate": 0.25,
        }
        
        driver._handle_charging_data(message)
        
        with driver.lock:
            assert driver.current_charging_session["energy_consumed"] == 5.5
            assert driver.current_charging_session["total_cost"] == 1.10
        
        logger.info("✓ PASS: Charging data updated successfully")
    except Exception as e:
        logger.error(f"✗ FAIL: Charging data update failed: {e}")
        return False
    
    # 测试4: 充电完成处理
    logger.info("\n[Test 4] Charging Completion")
    try:
        message = {
            "type": "charge_completion_notification",
            "session_id": "test_session_001",
            "energy_consumed_kwh": 10.0,
            "total_cost": 2.00,
        }
        
        driver._handle_charge_completion(message)
        
        with driver.lock:
            assert driver.current_charging_session is None
        
        assert len(driver.charging_history) == 1
        assert driver.charging_history[0]["session_id"] == "test_session_001"
        
        logger.info("✓ PASS: Charging completion handled successfully")
    except Exception as e:
        logger.error(f"✗ FAIL: Charging completion handling failed: {e}")
        return False
    
    # 测试5: 充电历史跟踪
    logger.info("\n[Test 5] Charging History Tracking")
    try:
        # 添加更多充电记录
        for i in range(2):
            record = {
                "session_id": f"session_{i+2}",
                "cp_id": f"CP{i+2:03d}",
                "completion_time": None,
                "energy_consumed": 10.0 + i,
                "total_cost": 2.0 + i * 0.5,
            }
            driver.charging_history.append(record)
        
        assert len(driver.charging_history) == 3
        assert driver.charging_history[0]["session_id"] == "test_session_001"
        assert driver.charging_history[2]["energy_consumed"] == 11.0
        
        logger.info("✓ PASS: Charging history tracked successfully")
    except Exception as e:
        logger.error(f"✗ FAIL: Charging history tracking failed: {e}")
        return False
    
    # 测试6: 消息处理覆盖
    logger.info("\n[Test 6] Message Handling Coverage")
    try:
        test_messages = [
            {
                "type": "charge_request_response",
                "status": "success",
                "session_id": "test_msg_1",
                "cp_id": "CP001",
            },
            {
                "type": "available_cps_response",
                "charging_points": [
                    {"cp_id": "CP001", "status": "ACTIVE"},
                ],
            },
            {
                "type": "CONNECTION_LOST",
            },
        ]
        
        for msg in test_messages:
            driver._handle_central_message(msg)
        
        logger.info("✓ PASS: All message types handled successfully")
    except Exception as e:
        logger.error(f"✗ FAIL: Message handling failed: {e}")
        return False
    
    # 测试7: 线程安全性
    logger.info("\n[Test 7] Thread Safety")
    try:
        import threading
        
        session = {
            "session_id": "thread_test",
            "cp_id": "CP_THREAD",
            "energy_consumed": 0.0,
            "total_cost": 0.0,
            "charging_rate": 0.25,
        }
        
        with driver.lock:
            driver.current_charging_session = session
        
        def update_session():
            for _ in range(5):
                with driver.lock:
                    if driver.current_charging_session:
                        driver.current_charging_session["energy_consumed"] += 0.1
        
        threads = [threading.Thread(target=update_session) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        with driver.lock:
            expected_value = 0.0 + 0.1 * 5 * 2
            assert abs(driver.current_charging_session["energy_consumed"] - expected_value) < 0.01
        
        logger.info("✓ PASS: Thread safety verified")
    except Exception as e:
        logger.error(f"✗ FAIL: Thread safety test failed: {e}")
        return False
    
    logger.info("\n" + "=" * 60)
    logger.info("All tests passed successfully! ✓")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    success = test_driver_basic_functionality()
    sys.exit(0 if success else 1)

