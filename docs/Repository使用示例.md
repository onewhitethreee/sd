# Repository 使用示例

## 目录
- [基础使用](#基础使用)
- [ChargingPointRepository 示例](#chargingpointrepository-示例)
- [DriverRepository 示例](#driverrepository-示例)
- [ChargingSessionRepository 示例](#chargingsessionrepository-示例)
- [组合使用示例](#组合使用示例)

---

## 基础使用

### 初始化

```python
from Common.Database.SqliteConnection import SqliteConnection
from Common.Database.ChargingPointRepository import ChargingPointRepository
from Common.Database.DriverRepository import DriverRepository
from Common.Database.ChargingSessionRepository import ChargingSessionRepository

# 创建数据库连接
db_connection = SqliteConnection("ev_central.db", "Core/BD/table.sql")

# 创建Repository实例
cp_repo = ChargingPointRepository(db_connection)
driver_repo = DriverRepository(db_connection)
session_repo = ChargingSessionRepository(db_connection)
```

---

## ChargingPointRepository 示例

### 1. 注册/更新充电桩

```python
# 注册新充电桩
success = cp_repo.insert_or_update(
    cp_id="CP001",
    location="北京市朝阳区",
    price_per_kwh=0.5,
    status="ACTIVE",
    last_connection_time=None,
    max_charging_rate_kw=11.0
)

if success:
    print("充电桩注册成功")
```

### 2. 查询充电桩

```python
# 根据ID获取充电桩
cp_info = cp_repo.get_by_id("CP001")
print(f"充电桩信息: {cp_info}")

# 检查充电桩是否存在
exists = cp_repo.exists("CP001")
print(f"充电桩是否存在: {exists}")

# 获取充电桩状态
status = cp_repo.get_status("CP001")
print(f"充电桩状态: {status}")
```

### 3. 更新充电桩

```python
# 更新充电桩状态
cp_repo.update_status("CP001", "CHARGING")

# 更新最后连接时间
from datetime import datetime, timezone
current_time = datetime.now(timezone.utc).isoformat()
cp_repo.update_last_connection_time("CP001", current_time)
```

### 4. 批量查询

```python
# 获取所有充电桩
all_cps = cp_repo.get_all()
print(f"总共有 {len(all_cps)} 个充电桩")

# 获取所有可用充电桩
available_cps = cp_repo.get_available()
print(f"可用充电桩: {len(available_cps)} 个")
for cp in available_cps:
    print(f"  - {cp['cp_id']}: {cp['location']}, {cp['price_per_kwh']}元/kWh")
```

---

## DriverRepository 示例

### 1. 注册司机

```python
# 注册新司机
success = driver_repo.register(
    driver_id="DRV001",
    username="张三"
)

if success:
    print("司机注册成功")
```

### 2. 查询司机

```python
# 根据ID获取司机信息
driver_info = driver_repo.get_by_id("DRV001")
print(f"司机信息: {driver_info}")

# 检查司机是否存在
exists = driver_repo.exists("DRV001")
print(f"司机是否存在: {exists}")

# 获取所有司机
all_drivers = driver_repo.get_all()
print(f"总共有 {len(all_drivers)} 个司机")
```

### 3. 更新司机信息

```python
# 更新司机用户名
driver_repo.update_username("DRV001", "张三丰")
```

---

## ChargingSessionRepository 示例

### 1. 创建充电会话

```python
import uuid
from datetime import datetime

# 创建新的充电会话
session_id = str(uuid.uuid4())
start_time = datetime.now().isoformat()

success = session_repo.create(
    session_id=session_id,
    cp_id="CP001",
    driver_id="DRV001",
    start_time=start_time
)

if success:
    print(f"充电会话 {session_id} 创建成功")
```

### 2. 更新充电会话

```python
# 更新充电数据
session_repo.update(
    session_id=session_id,
    energy_consumed_kwh=10.5,
    total_cost=5.25,
    status="in_progress"
)

# 完成充电会话
end_time = datetime.now().isoformat()
session_repo.update(
    session_id=session_id,
    end_time=end_time,
    energy_consumed_kwh=15.0,
    total_cost=7.5,
    status="completed"
)
```

### 3. 查询充电会话

```python
# 根据ID获取会话
session_info = session_repo.get_by_id(session_id)
print(f"会话信息: {session_info}")

# 检查会话是否活跃
is_active = session_repo.is_active(session_id)
print(f"会话是否活跃: {is_active}")

# 获取所有活跃会话
active_sessions = session_repo.get_active_sessions()
print(f"活跃会话数: {len(active_sessions)}")
```

### 4. 按条件查询

```python
# 获取指定充电桩的活跃会话
cp_active_sessions = session_repo.get_active_sessions_by_charging_point("CP001")
print(f"CP001的活跃会话: {len(cp_active_sessions)}")

# 获取指定司机的活跃会话
driver_active_sessions = session_repo.get_active_sessions_by_driver("DRV001")
print(f"DRV001的活跃会话: {len(driver_active_sessions)}")

# 获取指定充电桩的所有会话（包括历史）
all_cp_sessions = session_repo.get_sessions_by_charging_point("CP001")
print(f"CP001的所有会话: {len(all_cp_sessions)}")

# 获取指定司机的所有会话（包括历史）
all_driver_sessions = session_repo.get_sessions_by_driver("DRV001")
print(f"DRV001的所有会话: {len(all_driver_sessions)}")
```

---

## 组合使用示例

### 完整的充电流程示例

```python
from Common.Database.SqliteConnection import SqliteConnection
from Common.Database.ChargingPointRepository import ChargingPointRepository
from Common.Database.DriverRepository import DriverRepository
from Common.Database.ChargingSessionRepository import ChargingSessionRepository
from datetime import datetime, timezone
import uuid

# 初始化
db_connection = SqliteConnection("ev_central.db", "Core/BD/table.sql")
cp_repo = ChargingPointRepository(db_connection)
driver_repo = DriverRepository(db_connection)
session_repo = ChargingSessionRepository(db_connection)

# 1. 注册充电桩
cp_repo.insert_or_update(
    cp_id="CP001",
    location="北京市朝阳区",
    price_per_kwh=0.5,
    status="ACTIVE",
    last_connection_time=None,
    max_charging_rate_kw=11.0
)

# 2. 注册司机
driver_repo.register(driver_id="DRV001", username="张三")

# 3. 检查充电桩是否可用
cp_status = cp_repo.get_status("CP001")
if cp_status == "ACTIVE":
    # 4. 创建充电会话
    session_id = str(uuid.uuid4())
    start_time = datetime.now().isoformat()

    session_repo.create(
        session_id=session_id,
        cp_id="CP001",
        driver_id="DRV001",
        start_time=start_time
    )

    # 5. 更新充电桩状态为充电中
    cp_repo.update_status("CP001", "CHARGING")

    # 6. 模拟充电过程（更新充电数据）
    import time
    time.sleep(1)  # 模拟充电

    session_repo.update(
        session_id=session_id,
        energy_consumed_kwh=5.0,
        total_cost=2.5,
        status="in_progress"
    )

    # 7. 完成充电
    end_time = datetime.now().isoformat()
    session_repo.update(
        session_id=session_id,
        end_time=end_time,
        energy_consumed_kwh=10.0,
        total_cost=5.0,
        status="completed"
    )

    # 8. 更新充电桩状态为可用
    cp_repo.update_status("CP001", "ACTIVE")

    # 9. 查看结果
    final_session = session_repo.get_by_id(session_id)
    print(f"充电完成！")
    print(f"消耗电量: {final_session['energy_consumed_kwh']} kWh")
    print(f"总费用: {final_session['total_cost']} 元")
    print(f"开始时间: {final_session['start_time']}")
    print(f"结束时间: {final_session['end_time']}")
```

### 批量查询示例

```python
# 获取系统概览
print("=== 系统概览 ===")

# 所有充电桩
all_cps = cp_repo.get_all()
print(f"总充电桩数: {len(all_cps)}")

# 可用充电桩
available_cps = cp_repo.get_available()
print(f"可用充电桩数: {len(available_cps)}")

# 所有司机
all_drivers = driver_repo.get_all()
print(f"总司机数: {len(all_drivers)}")

# 活跃会话
active_sessions = session_repo.get_active_sessions()
print(f"活跃充电会话数: {len(active_sessions)}")

# 所有会话
all_sessions = session_repo.get_all()
print(f"总会话数: {len(all_sessions)}")

# 详细列表
print("\n=== 可用充电桩 ===")
for cp in available_cps:
    print(f"{cp['cp_id']}: {cp['location']} - {cp['price_per_kwh']}元/kWh")

print("\n=== 活跃充电会话 ===")
for session in active_sessions:
    print(f"会话 {session['session_id'][:8]}... - CP: {session['cp_id']}, 司机: {session['driver_id']}")
```

---

## 错误处理示例

```python
try:
    # 尝试创建充电会话
    session_id = str(uuid.uuid4())
    start_time = datetime.now().isoformat()

    # 检查充电桩是否存在
    if not cp_repo.exists("CP999"):
        print("错误: 充电桩不存在")
        # 可以选择创建充电桩或抛出异常
        raise ValueError("充电桩CP999不存在")

    # 检查司机是否存在
    if not driver_repo.exists("DRV999"):
        print("警告: 司机不存在，正在自动注册...")
        driver_repo.register("DRV999", "新司机")

    # 创建会话
    success = session_repo.create(
        session_id=session_id,
        cp_id="CP999",
        driver_id="DRV999",
        start_time=start_time
    )

    if success:
        print("充电会话创建成功")
    else:
        print("充电会话创建失败")

except ValueError as e:
    print(f"业务逻辑错误: {e}")
except Exception as e:
    print(f"系统错误: {e}")
```

---

## 总结

通过Repository模式，我们实现了：

1. **清晰的职责分离**: 每个Repository只负责一张表的操作
2. **简洁的API**: 方法名清晰易懂，参数明确
3. **易于维护**: 数据库操作集中管理
4. **易于测试**: 可以轻松Mock Repository进行单元测试
5. **类型安全**: 所有方法都有清晰的参数和返回值定义

使用这些Repository类，可以大大简化业务逻辑层的代码，提高代码质量和可维护性。
