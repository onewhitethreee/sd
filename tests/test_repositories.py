"""
Repository 功能测试脚本

测试 ChargingPointRepository, DriverRepository, ChargingSessionRepository
"""

import os
import sys
import uuid
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Common.Database.SqliteConnection import SqliteConnection
from Common.Database.ChargingPointRepository import ChargingPointRepository
from Common.Database.DriverRepository import DriverRepository
from Common.Database.ChargingSessionRepository import ChargingSessionRepository


def test_charging_point_repository():
    """测试 ChargingPointRepository"""
    print("\n" + "=" * 60)
    print("测试 ChargingPointRepository")
    print("=" * 60)

    # 创建测试数据库连接
    db_path = "test_repository.db"
    sql_schema = os.path.join(os.path.dirname(__file__), "..", "Core", "BD", "table.sql")

    # 删除旧的测试数据库
    if os.path.exists(db_path):
        os.remove(db_path)

    db_conn = SqliteConnection(db_path, sql_schema)
    repo = ChargingPointRepository(db_conn)

    # 测试插入
    print("\n1. 测试插入充电桩...")
    success = repo.insert_or_update(
        cp_id="CP001",
        location="测试地点1",
        price_per_kwh=0.5,
        status="ACTIVE",
        last_connection_time=None,
    )
    print(f"   插入结果: {'成功' if success else '失败'}")

    # 测试查询
    print("\n2. 测试查询充电桩...")
    cp = repo.get_by_id("CP001")
    print(f"   查询结果: {cp}")

    # 测试存在性检查
    print("\n3. 测试存在性检查...")
    exists = repo.exists("CP001")
    print(f"   CP001存在: {exists}")

    # 测试更新状态
    print("\n4. 测试更新状态...")
    repo.update_status("CP001", "CHARGING")
    status = repo.get_status("CP001")
    print(f"   新状态: {status}")

    # 测试获取所有充电桩
    print("\n5. 测试获取所有充电桩...")
    # 添加更多充电桩
    repo.insert_or_update("CP002", "测试地点2", 0.6, "ACTIVE", None, 22.0)
    repo.insert_or_update("CP003", "测试地点3", 0.7, "STOPPED", None, 7.0)

    all_cps = repo.get_all()
    print(f"   总充电桩数: {len(all_cps)}")

    # 测试获取可用充电桩
    print("\n6. 测试获取可用充电桩...")
    available = repo.get_available()
    print(f"   可用充电桩数: {len(available)}")
    for cp in available:
        print(f"   - {cp['cp_id']}: {cp['location']}")

    print("\n[OK] ChargingPointRepository 测试完成")


def test_driver_repository():
    """测试 DriverRepository"""
    print("\n" + "=" * 60)
    print("测试 DriverRepository")
    print("=" * 60)

    db_path = "test_repository.db"
    db_conn = SqliteConnection(db_path)
    repo = DriverRepository(db_conn)

    # 测试注册司机
    print("\n1. 测试注册司机...")
    success = repo.register("DRV001", "张三")
    print(f"   注册结果: {'成功' if success else '失败'}")

    # 测试查询司机
    print("\n2. 测试查询司机...")
    driver = repo.get_by_id("DRV001")
    print(f"   查询结果: {driver}")

    # 测试存在性检查
    print("\n3. 测试存在性检查...")
    exists = repo.exists("DRV001")
    print(f"   DRV001存在: {exists}")

    # 测试更新用户名
    print("\n4. 测试更新用户名...")
    repo.update_username("DRV001", "张三丰")
    driver = repo.get_by_id("DRV001")
    print(f"   新用户名: {driver['username']}")

    # 测试获取所有司机
    print("\n5. 测试获取所有司机...")
    repo.register("DRV002", "李四")
    repo.register("DRV003", "王五")

    all_drivers = repo.get_all()
    print(f"   总司机数: {len(all_drivers)}")
    for driver in all_drivers:
        print(f"   - {driver['driver_id']}: {driver['username']}")

    print("\n[OK] DriverRepository 测试完成")


def test_charging_session_repository():
    """测试 ChargingSessionRepository"""
    print("\n" + "=" * 60)
    print("测试 ChargingSessionRepository")
    print("=" * 60)

    db_path = "test_repository.db"
    db_conn = SqliteConnection(db_path)
    repo = ChargingSessionRepository(db_conn)

    # 测试创建会话
    print("\n1. 测试创建充电会话...")
    session_id = str(uuid.uuid4())
    start_time = datetime.now().isoformat()

    success = repo.create(session_id, "CP001", "DRV001", start_time)
    print(f"   创建结果: {'成功' if success else '失败'}")

    # 测试查询会话
    print("\n2. 测试查询充电会话...")
    session = repo.get_by_id(session_id)
    print(f"   查询结果: {session}")

    # 测试检查会话是否活跃
    print("\n3. 测试检查会话是否活跃...")
    is_active = repo.is_active(session_id)
    print(f"   会话是否活跃: {is_active}")

    # 测试更新会话
    print("\n4. 测试更新充电会话...")
    repo.update(
        session_id=session_id,
        energy_consumed_kwh=10.5,
        total_cost=5.25,
        status="in_progress",
    )
    session = repo.get_by_id(session_id)
    print(f"   电量: {session['energy_consumed_kwh']} kWh")
    print(f"   费用: {session['total_cost']} 元")

    # 测试完成会话
    print("\n5. 测试完成充电会话...")
    end_time = datetime.now().isoformat()
    repo.update(
        session_id=session_id,
        end_time=end_time,
        energy_consumed_kwh=15.0,
        total_cost=7.5,
        status="completed",
    )

    session = repo.get_by_id(session_id)
    print(f"   最终电量: {session['energy_consumed_kwh']} kWh")
    print(f"   最终费用: {session['total_cost']} 元")
    print(f"   状态: {session['status']}")

    # 测试获取活跃会话
    print("\n6. 测试获取活跃会话...")
    # 创建另一个活跃会话
    session_id2 = str(uuid.uuid4())
    repo.create(session_id2, "CP002", "DRV002", start_time)

    active_sessions = repo.get_active_sessions()
    print(f"   活跃会话数: {len(active_sessions)}")

    # 测试按充电桩查询
    print("\n7. 测试按充电桩查询活跃会话...")
    cp_sessions = repo.get_active_sessions_by_charging_point("CP001")
    print(f"   CP001的活跃会话数: {len(cp_sessions)}")

    # 测试按司机查询
    print("\n8. 测试按司机查询活跃会话...")
    driver_sessions = repo.get_active_sessions_by_driver("DRV002")
    print(f"   DRV002的活跃会话数: {len(driver_sessions)}")

    # 测试获取所有会话
    print("\n9. 测试获取所有会话...")
    all_sessions = repo.get_all()
    print(f"   总会话数: {len(all_sessions)}")
    for session in all_sessions:
        print(
            f"   - {session['session_id'][:8]}... CP:{session['cp_id']} 司机:{session['driver_id']} 状态:{session['status']}"
        )

    print("\n[OK] ChargingSessionRepository 测试完成")


def test_integration():
    """集成测试 - 完整的充电流程"""
    print("\n" + "=" * 60)
    print("集成测试 - 完整充电流程")
    print("=" * 60)

    db_path = "test_repository.db"
    db_conn = SqliteConnection(db_path)

    cp_repo = ChargingPointRepository(db_conn)
    driver_repo = DriverRepository(db_conn)
    session_repo = ChargingSessionRepository(db_conn)

    # 场景：一个司机使用一个充电桩完成充电
    print("\n场景：司机DRV999在CP999充电")

    # 1. 注册充电桩
    print("\n1. 注册充电桩CP999...")
    cp_repo.insert_or_update(
        cp_id="CP999",
        location="集成测试充电桩",
        price_per_kwh=0.55,
        status="ACTIVE",
        last_connection_time=None,
    )

    # 2. 注册司机
    print("2. 注册司机DRV999...")
    driver_repo.register("DRV999", "测试司机")

    # 3. 检查充电桩状态
    print("3. 检查充电桩状态...")
    status = cp_repo.get_status("CP999")
    print(f"   充电桩状态: {status}")

    if status == "ACTIVE":
        # 4. 创建充电会话
        print("4. 创建充电会话...")
        session_id = str(uuid.uuid4())
        start_time = datetime.now().isoformat()
        session_repo.create(session_id, "CP999", "DRV999", start_time)

        # 5. 更新充电桩状态为充电中
        print("5. 更新充电桩状态为充电中...")
        cp_repo.update_status("CP999", "CHARGING")

        # 6. 模拟充电数据更新
        print("6. 模拟充电数据更新...")
        session_repo.update(
            session_id=session_id,
            energy_consumed_kwh=5.0,
            total_cost=2.75,
            status="in_progress",
        )

        # 7. 完成充电
        print("7. 完成充电...")
        end_time = datetime.now().isoformat()
        session_repo.update(
            session_id=session_id,
            end_time=end_time,
            energy_consumed_kwh=20.0,
            total_cost=11.0,
            status="completed",
        )

        # 8. 恢复充电桩状态
        print("8. 恢复充电桩状态为可用...")
        cp_repo.update_status("CP999", "ACTIVE")

        # 9. 显示结果
        print("\n充电完成！详细信息：")
        session = session_repo.get_by_id(session_id)
        cp = cp_repo.get_by_id("CP999")
        driver = driver_repo.get_by_id("DRV999")

        print(f"   充电桩: {cp['cp_id']} - {cp['location']}")
        print(f"   司机: {driver['driver_id']} - {driver['username']}")
        print(f"   消耗电量: {session['energy_consumed_kwh']} kWh")
        print(f"   总费用: {session['total_cost']} 元")
        print(f"   开始时间: {session['start_time']}")
        print(f"   结束时间: {session['end_time']}")

    print("\n[OK] 集成测试完成")


def cleanup():
    """清理测试数据库"""
    print("\n" + "=" * 60)
    print("清理测试数据库")
    print("=" * 60)

    import time
    db_path = "test_repository.db"
    if os.path.exists(db_path):
        # 等待一下，确保所有连接都已关闭
        time.sleep(0.5)
        try:
            os.remove(db_path)
            print(f"已删除测试数据库: {db_path}")
        except PermissionError:
            print(f"警告: 无法删除测试数据库 {db_path}，可能仍在使用中")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Repository 功能测试")
    print("=" * 60)

    try:
        # 运行所有测试
        test_charging_point_repository()
        test_driver_repository()
        test_charging_session_repository()
        test_integration()

        print("\n" + "=" * 60)
        print("所有测试完成！ [SUCCESS]")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # 清理
        cleanup()
