# Repository 架构重构总结

## 概述
本次重构将数据库操作从业务逻辑层（ChargingPoint、ChargingSession）中分离出来，为三张数据库表分别创建了专门的Repository类，实现了更清晰的分层架构。

## 架构设计

### 1. 基础架构层 (Common/Database)

#### BaseRepository (抽象基类)
- **位置**: `Common/Database/BaseRepository.py`
- **职责**: 定义所有Repository的通用接口和行为
- **主要方法**:
  - `get_connection()`: 获取数据库连接
  - `execute_query()`: 执行查询语句
  - `execute_update()`: 执行更新语句
  - `get_table_name()`: 抽象方法，由子类实现

### 2. Repository 实现层

#### ChargingPointRepository
- **位置**: `Common/Database/ChargingPointRepository.py`
- **对应表**: `ChargingPoints`
- **主要方法**:
  - `insert_or_update()`: 插入或更新充电桩
  - `update_status()`: 更新状态
  - `update_last_connection_time()`: 更新最后连接时间
  - `get_by_id()`: 根据ID获取充电桩
  - `get_status()`: 获取状态
  - `exists()`: 检查是否存在
  - `get_all()`: 获取所有充电桩
  - `get_available()`: 获取可用充电桩
  - `set_all_status()`: 设置所有充电桩状态

#### DriverRepository
- **位置**: `Common/Database/DriverRepository.py`
- **对应表**: `Drivers`
- **主要方法**:
  - `register()`: 注册司机
  - `get_by_id()`: 根据ID获取司机
  - `exists()`: 检查是否存在
  - `get_all()`: 获取所有司机
  - `update_username()`: 更新用户名
  - `delete()`: 删除司机

#### ChargingSessionRepository
- **位置**: `Common/Database/ChargingSessionRepository.py`
- **对应表**: `ChargingSessions`
- **主要方法**:
  - `create()`: 创建充电会话
  - `update()`: 更新充电会话
  - `get_by_id()`: 根据ID获取会话
  - `get_active_sessions()`: 获取所有活跃会话
  - `get_all()`: 获取所有会话
  - `get_active_sessions_by_charging_point()`: 获取充电桩的活跃会话
  - `get_active_sessions_by_driver()`: 获取司机的活跃会话
  - `get_sessions_by_charging_point()`: 获取充电桩的所有会话
  - `get_sessions_by_driver()`: 获取司机的所有会话
  - `exists()`: 检查会话是否存在
  - `is_active()`: 检查会话是否活跃

### 3. 业务逻辑层更新

#### ChargingPoint 类
- **位置**: `Core/Central/ChargingPoint.py`
- **更新内容**:
  - 引入 `ChargingPointRepository`
  - 所有数据库操作改为使用 `self.repository` 而非 `self.db_manager`
  - 保留业务逻辑和连接管理功能

#### ChargingSession 类
- **位置**: `Core/Central/ChargingSession.py`
- **更新内容**:
  - 引入三个Repository: `ChargingSessionRepository`、`ChargingPointRepository`、`DriverRepository`
  - 所有数据库操作改为使用对应的Repository
  - 保留业务逻辑和会话管理功能

## 架构优势

### 1. 关注点分离
- **数据访问层**: Repository负责所有SQL操作
- **业务逻辑层**: ChargingPoint/ChargingSession负责业务规则和流程控制
- **连接管理层**: SqliteConnection负责数据库连接管理

### 2. 可维护性提升
- 每个Repository只关注一张表，职责单一
- 数据库操作集中在Repository中，便于统一管理和修改
- 代码结构清晰，易于理解和维护

### 3. 可测试性增强
- Repository可以独立测试
- 业务逻辑层可以通过Mock Repository进行单元测试
- 降低了测试的复杂度

### 4. 可扩展性
- 新增表时，只需创建对应的Repository
- 修改数据库操作时，不影响业务逻辑层
- 可以轻松切换到其他数据库（只需实现新的Repository）

### 5. 代码复用
- BaseRepository提供通用的数据库操作方法
- 避免了在每个Repository中重复编写相同代码

## 使用示例

### ChargingPoint 使用示例
```python
# 之前（直接使用db_manager）
self.db_manager.insert_or_update_charging_point(cp_id, location, price, status, time)

# 现在（使用Repository）
self.repository.insert_or_update(cp_id, location, price, status, time)
```

### ChargingSession 使用示例
```python
# 之前（直接使用db_manager）
self.db_manager.create_charging_session(session_id, cp_id, driver_id, start_time)

# 现在（使用Repository）
self.repository.create(session_id, cp_id, driver_id, start_time)
```

## 数据库表与Repository映射

| 数据库表 | Repository类 | 文件路径 |
|---------|-------------|---------|
| ChargingPoints | ChargingPointRepository | Common/Database/ChargingPointRepository.py |
| Drivers | DriverRepository | Common/Database/DriverRepository.py |
| ChargingSessions | ChargingSessionRepository | Common/Database/ChargingSessionRepository.py |

## 后续优化建议

### 1. SqliteConnection 重构（待完成）
- 移除具体业务方法（如 `insert_or_update_charging_point`）
- 仅保留连接管理功能
- 可以参考当前的BaseRepository设计

### 2. 事务管理
- 在Repository中添加事务支持
- 处理跨表操作时的事务一致性

### 3. 缓存机制
- 在Repository层添加缓存
- 减少数据库访问频率，提升性能

### 4. 异常处理
- 统一异常处理机制
- 定义自定义异常类型

### 5. 日志记录
- 增强Repository的日志记录
- 记录SQL执行时间和参数，便于调试和性能优化

## 总结

本次重构成功实现了数据访问层的抽象，将三张数据库表的操作分别封装到独立的Repository类中。这种设计模式提高了代码的可维护性、可测试性和可扩展性，为项目的长期发展奠定了良好的基础。

所有现有功能保持不变，只是改变了内部实现方式，确保了向后兼容性。
