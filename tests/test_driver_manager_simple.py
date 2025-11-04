"""
简化的DriverManager测试 - 仅测试连接管理功能
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Common.Config.CustomLogger import CustomLogger


class MockChargingSession:
    """模拟的ChargingSession，用于测试"""

    def get_active_sessions_for_driver(self, driver_id):
        # 返回空列表作为测试
        return []


def test_driver_manager_basic():
    """测试DriverManager基本功能（不依赖数据库）"""
    from Core.Central.DriverManager import DriverManager

    print("=" * 60)
    print("DriverManager 基本功能测试")
    print("=" * 60)

    # 初始化
    logger = CustomLogger.get_logger()
    mock_session_manager = MockChargingSession()
    driver_manager = DriverManager(logger, mock_session_manager)

    # 测试1: 注册Driver连接
    print("\n[Test 1] Register driver connection")
    success = driver_manager.register_driver_connection("driver_001", "client_123")
    assert success, "Failed to register driver"
    print("PASS - Driver registered successfully")

    # 测试2: 查询Driver连接
    print("\n[Test 2] Query driver client_id")
    client_id = driver_manager.get_driver_client_id("driver_001")
    assert client_id == "client_123", f"Expected client_123, got {client_id}"
    print(f"PASS - Driver client_id correct: {client_id}")

    # 测试3: 反向查询
    print("\n[Test 3] Reverse query by client_id")
    driver_id = driver_manager.get_driver_by_client_id("client_123")
    assert driver_id == "driver_001", f"Expected driver_001, got {driver_id}"
    print(f"PASS - Reverse query correct: {driver_id}")

    # 测试4: 检查连接状态
    print("\n[Test 4] Check connection status")
    is_connected = driver_manager.is_driver_connected("driver_001")
    assert is_connected, "Driver should be connected"
    print("PASS - Driver is connected")

    # 测试5: 获取连接数量
    print("\n[Test 5] Get connection count")
    count = driver_manager.get_connection_count()
    assert count == 1, f"Expected 1 connection, got {count}"
    print(f"PASS - Connection count correct: {count}")

    # 测试6: 获取所有连接的Driver
    print("\n[Test 6] Get all connected drivers")
    drivers = driver_manager.get_all_connected_drivers()
    assert len(drivers) == 1 and drivers[0] == "driver_001"
    print(f"PASS - Connected drivers: {drivers}")

    # 测试7: 获取Driver信息
    print("\n[Test 7] Get driver info")
    info = driver_manager.get_driver_info("driver_001")
    assert info is not None
    assert info["driver_id"] == "driver_001"
    assert info["client_id"] == "client_123"
    assert info["is_connected"] == True
    print(f"PASS - Driver info: {info}")

    # 测试8: 处理断开连接
    print("\n[Test 8] Handle driver disconnect")
    disconnected_driver, sessions = driver_manager.handle_driver_disconnect("client_123")
    assert disconnected_driver == "driver_001"
    assert driver_manager.get_connection_count() == 0
    assert not driver_manager.is_driver_connected("driver_001")
    print(f"PASS - Disconnect handled: driver={disconnected_driver}, sessions={sessions}")

    # 测试9: 重复注册
    print("\n[Test 9] Test re-connection")
    driver_manager.register_driver_connection("driver_002", "client_456")
    driver_manager.register_driver_connection(
        "driver_002", "client_789"
    )  # Re-connect with new client
    client_id = driver_manager.get_driver_client_id("driver_002")
    assert client_id == "client_789"
    print(f"PASS - Re-connection handled, new client_id: {client_id}")

    # 测试10: 手动注销连接
    print("\n[Test 10] Manual unregister")
    success = driver_manager.unregister_driver_connection("driver_002")
    assert success
    assert not driver_manager.is_driver_connected("driver_002")
    print("PASS - Manual unregister successful")

    print("\n" + "=" * 60)
    print("All tests PASSED!")
    print("=" * 60)


def test_comparison_with_old_design():
    """对比测试：展示新设计的优势"""
    print("\n" + "=" * 60)
    print("Design Comparison Test")
    print("=" * 60)

    from Core.Central.DriverManager import DriverManager

    logger = CustomLogger.get_logger()
    mock_session_manager = MockChargingSession()
    driver_manager = DriverManager(logger, mock_session_manager)

    # 旧设计需要维护3个字典
    print("\n[Old Design]")
    print("  - _driver_connections = {}")
    print("  - _client_to_driver = {}")
    print("  - _driver_active_sessions = {}  # <-- Redundant with DB!")

    # 新设计只需要2个字典 + 委托查询
    print("\n[New Design]")
    print("  - _driver_connections = {}  (in DriverManager)")
    print("  - _client_to_driver = {}    (in DriverManager)")
    print("  - Active sessions: Query from ChargingSession (Single source of truth!)")

    # 演示新设计的使用
    print("\n[Demo] Register and query active sessions")
    driver_manager.register_driver_connection("driver_test", "client_test")

    # 新设计：通过DriverManager查询活跃会话（委托给ChargingSession）
    sessions = driver_manager.get_driver_active_sessions("driver_test")
    print(f"  Active sessions: {sessions} (from database, not memory!)")

    print("\n" + "=" * 60)
    print("Benefits of new design:")
    print("  1. Single Responsibility: DriverManager only manages connections")
    print("  2. No data redundancy: Sessions stored in DB only")
    print("  3. No sync issues: DB is the single source of truth")
    print("  4. Consistent architecture: Like ChargingPoint pattern")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_driver_manager_basic()
        test_comparison_with_old_design()
        print("\n SUCCESS: All tests completed!")
    except AssertionError as e:
        print(f"\n FAILED: Test assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
