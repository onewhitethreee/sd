"""
测试DriverManager重构的正确性
"""

import os
import sys
import uuid

# 设置UTF-8编码输出
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Common.Config.CustomLogger import CustomLogger
from Common.Database.SqliteConnection import SqliteConnection
from Core.Central.ChargingSession import ChargingSession
from Core.Central.DriverManager import DriverManager


def test_driver_manager():
    """测试DriverManager基本功能"""
    print("=" * 60)
    print("测试 DriverManager 基本功能")
    print("=" * 60)

    # 初始化
    logger = CustomLogger.get_logger()
    db_manager = SqliteConnection(":memory:")  # 使用内存数据库测试
    charging_session_manager = ChargingSession(logger, db_manager)
    driver_manager = DriverManager(logger, charging_session_manager)

    # 测试1: 注册Driver连接
    print("\n[测试1] 注册Driver连接")
    success = driver_manager.register_driver_connection("driver_001", "client_123")
    assert success, "注册Driver连接失败"
    print("✓ Driver注册成功")

    # 测试2: 查询Driver连接
    print("\n[测试2] 查询Driver连接")
    client_id = driver_manager.get_driver_client_id("driver_001")
    assert client_id == "client_123", f"预期 client_123, 实际 {client_id}"
    print(f"✓ Driver client_id 查询正确: {client_id}")

    # 测试3: 反向查询
    print("\n[测试3] 反向查询")
    driver_id = driver_manager.get_driver_by_client_id("client_123")
    assert driver_id == "driver_001", f"预期 driver_001, 实际 {driver_id}"
    print(f"✓ 反向查询正确: {driver_id}")

    # 测试4: 检查连接状态
    print("\n[测试4] 检查连接状态")
    is_connected = driver_manager.is_driver_connected("driver_001")
    assert is_connected, "Driver应该在线"
    print("✓ Driver在线状态正确")

    # 测试5: 获取连接数量
    print("\n[测试5] 获取连接数量")
    count = driver_manager.get_connection_count()
    assert count == 1, f"预期1个连接, 实际 {count}"
    print(f"✓ 连接数量正确: {count}")

    # 测试6: 处理断开连接
    print("\n[测试6] 处理Driver断开连接")
    disconnected_driver, sessions = driver_manager.handle_driver_disconnect("client_123")
    assert disconnected_driver == "driver_001", f"预期 driver_001, 实际 {disconnected_driver}"
    assert driver_manager.get_connection_count() == 0, "断开后连接数应为0"
    print(f"✓ 断开连接处理正确: {disconnected_driver}, 会话数: {len(sessions)}")

    # 测试7: 重复注册
    print("\n[测试7] 测试重复注册")
    driver_manager.register_driver_connection("driver_002", "client_456")
    driver_manager.register_driver_connection("driver_002", "client_789")  # 重新连接
    client_id = driver_manager.get_driver_client_id("driver_002")
    assert client_id == "client_789", f"重连后应该更新为新的client_id"
    print(f"✓ 重复注册处理正确，新 client_id: {client_id}")

    print("\n" + "=" * 60)
    print("所有测试通过! ✓")
    print("=" * 60)


def test_driver_manager_with_sessions():
    """测试DriverManager与ChargingSession的集成"""
    print("\n" + "=" * 60)
    print("测试 DriverManager 与 ChargingSession 集成")
    print("=" * 60)

    # 初始化
    logger = CustomLogger.get_logger()
    db_manager = SqliteConnection(":memory:")
    charging_session_manager = ChargingSession(logger, db_manager)
    driver_manager = DriverManager(logger, charging_session_manager)

    # 创建充电桩和会话
    print("\n[准备] 创建测试数据")
    cp_id = "CP_TEST_001"
    driver_id = "driver_test_001"

    # 插入充电桩
    db_manager.insert_or_update_charging_point(
        cp_id=cp_id,
        location="Test Location",
        price_per_kwh=0.5,
        status="ACTIVE",
        last_connection_time=None,
    )

    # 创建充电会话
    session_id, _ = charging_session_manager.create_charging_session(cp_id, driver_id)
    assert session_id, "创建充电会话失败"
    print(f"✓ 测试会话创建成功: {session_id}")

    # 注册Driver连接
    driver_manager.register_driver_connection(driver_id, "client_test_123")

    # 测试: 查询Driver的活跃会话
    print("\n[测试] 查询Driver活跃会话")
    active_sessions = driver_manager.get_driver_active_sessions(driver_id)
    assert len(active_sessions) == 1, f"预期1个活跃会话, 实际 {len(active_sessions)}"
    assert active_sessions[0]["session_id"] == session_id
    print(f"✓ 活跃会话查询正确: {active_sessions[0]['session_id']}")

    # 测试: 断开连接时获取活跃会话
    print("\n[测试] 断开连接时获取活跃会话")
    disconnected_driver, session_ids = driver_manager.handle_driver_disconnect(
        "client_test_123"
    )
    assert disconnected_driver == driver_id
    assert len(session_ids) == 1
    assert session_ids[0] == session_id
    print(f"✓ 断开时活跃会话获取正确: {session_ids}")

    print("\n" + "=" * 60)
    print("集成测试通过! ✓")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_driver_manager()
        test_driver_manager_with_sessions()
        print("\n🎉 所有测试完成!")
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 运行错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
