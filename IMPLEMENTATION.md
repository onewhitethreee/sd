# 电动汽车充电系统实现文档

## 系统概述

本系统是一个分布式电动汽车充电管理系统，包含充电点引擎、监控模块、中央控制系统和司机应用程序。系统采用Socket通信和Kafka消息队列进行组件间通信。

## 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   EV_Driver     │    │   EV_CP_M       │    │   EV_Central    │
│   (司机应用)     │    │   (监控模块)     │    │   (中央控制)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   EV_CP_E       │
                    │   (充电引擎)     │
                    └─────────────────┘
```

## 核心组件

### 1. EV_Central (中央控制系统)
**文件位置**: `Core/Central/EV_Central.py`

**主要功能**:
- 管理所有充电点的注册和状态
- 处理充电请求和授权
- 维护充电会话记录
- 处理故障通知和恢复

**核心方法**:
- `_handle_register_message()` - 处理充电点注册
- `_handle_charge_request_message()` - 处理充电请求
- `_handle_charge_completion_message()` - 处理充电完成
- `_handle_fault_notification_message()` - 处理故障通知
- `_handle_heartbeat_message()` - 处理心跳消息

### 2. EV_CP_M (充电点监控模块)
**文件位置**: `Charging_point/Monitor/EC_CP_M.py`

**主要功能**:
- 监控充电点引擎的健康状态
- 与中央系统通信
- 处理故障检测和报告
- 管理重连机制

**核心方法**:
- `_check_engine_health()` - 健康检查
- `_report_failure()` - 故障报告
- `_reconnect_services()` - 重连服务
- `update_cp_status()` - 状态更新

### 3. EV_CP_E (充电点引擎)
**文件位置**: `Charging_point/Engine/EV_CP_E.py`

**主要功能**:
- 执行实际的充电操作
- 响应监控模块的命令
- 处理充电会话的开始和结束
- 提供健康状态信息

**核心方法**:
- `_start_charging_session()` - 开始充电会话
- `_stop_charging_session()` - 停止充电会话
- `_handle_health_check()` - 处理健康检查
- `get_current_status()` - 获取当前状态

### 4. EV_Driver (司机应用程序)
**文件位置**: `Driver/EV_Driver.py`

**主要功能**:
- 司机与充电系统的交互界面
- 发送充电请求
- 接收充电状态更新

## 数据库设计

### 表结构

#### ChargingPoints (充电点表)
```sql
CREATE TABLE IF NOT EXISTS `ChargingPoints` (
  `cp_id` text PRIMARY KEY,
  `location` varchar(255),
  `price_per_kwh` decimal(10, 4),
  `status` TEXT NOT NULL DEFAULT 'unknown' CHECK (
    `status` IN ('ACTIVE', 'STOPPED', 'DISCONNECTED', 'FAULTY', 'CHARGING')
  ),
  `last_connection_time` DATETIME
);
```

#### Drivers (司机表)
```sql
CREATE TABLE IF NOT EXISTS `Drivers` (
  `driver_id` text PRIMARY KEY,
  `username` varchar(255),
  `created_at` DATETIME
);
```

#### ChargingSessions (充电会话表)
```sql
CREATE TABLE IF NOT EXISTS `ChargingSessions` (
  `session_id` text PRIMARY KEY,
  `cp_id` text,
  `driver_id` text,
  `start_time` DATETIME,
  `end_time` DATETIME,
  `energy_consumed_kwh` decimal(12, 2),
  `total_cost` decimal(12, 2),
  `status` TEXT NOT NULL DEFAULT 'requested' CHECK (
    `status` IN ('requested', 'authorized', 'in_progress', 'completed', 'cancelled', 'failed')
  ),
  FOREIGN KEY (`cp_id`) REFERENCES `ChargingPoints` (`cp_id`),
  FOREIGN KEY (`driver_id`) REFERENCES `Drivers` (`driver_id`)
);
```

## 消息协议

### 消息类型

#### 1. 注册消息
```json
{
  "type": "register_request",
  "message_id": "uuid",
  "id": "cp_001",
  "location": "Location_Info",
  "price_per_kwh": 0.20
}
```

#### 2. 充电请求消息
```json
{
  "type": "charge_request",
  "message_id": "uuid",
  "cp_id": "cp_001",
  "driver_id": "driver_001"
}
```

#### 3. 健康检查消息
```json
{
  "type": "health_check_request",
  "message_id": "uuid",
  "id": "cp_001",
  "timestamp": 1234567890
}
```

#### 4. 故障通知消息
```json
{
  "type": "fault_notification",
  "message_id": "uuid",
  "id": "cp_001",
  "failure_info": "Connection timeout"
}
```

## 状态管理

### 充电点状态
- `ACTIVE` - 活跃，可以接受充电请求
- `CHARGING` - 正在充电
- `STOPPED` - 停止服务
- `FAULTY` - 故障状态
- `DISCONNECTED` - 断开连接

### 充电会话状态
- `requested` - 已请求
- `authorized` - 已授权
- `in_progress` - 进行中
- `completed` - 已完成
- `cancelled` - 已取消
- `failed` - 失败

## 故障处理机制

### 1. 健康检查
- 监控模块每30秒向引擎发送健康检查请求
- 2分钟无响应则判定为故障
- 自动触发重连机制

### 2. 故障恢复
- 自动重连机制（最多5次重试）
- 故障状态自动报告给中央系统
- 恢复后自动更新状态为活跃

### 3. 安全模式
- Monitor断开连接时，引擎进入安全模式
- 自动停止当前充电会话
- 等待Monitor重连

## 配置管理

### 环境变量配置
系统使用 `ConfigManager` 类管理配置，支持以下配置项：

- `DEBUG_MODE` - 调试模式
- `BROKER_ADDRESS` - Kafka代理地址
- `DB_PATH` - 数据库文件路径
- `LISTEN_PORT` - 监听端口
- `IP_PORT_EV_CP_E` - 充电引擎地址
- `IP_PORT_EV_CP_CENTRAL` - 中央系统地址

## 部署说明

### 依赖项
```txt
python-dotenv==1.0.0
kafka-python==2.0.2
```

### 启动顺序
1. 启动Kafka服务（使用docker-compose.yml）
2. 启动EV_Central（中央控制系统）
3. 启动EV_CP_M（监控模块）
4. 启动EV_CP_E（充电引擎）
5. 启动EV_Driver（司机应用）

### 测试
系统包含测试文件：
- `Test/test_create_sqlite.py` - 数据库测试
- `Test/test_sServer.py` - 服务器测试

## 扩展功能

### 待实现功能
1. **Kafka集成** - 消息队列通信
2. **Web管理界面** - 系统监控面板
3. **支付集成** - 充电费用处理
4. **通知系统** - 故障和状态通知
5. **数据分析** - 充电数据统计

### 性能优化
1. 连接池管理
2. 消息批处理
3. 数据库索引优化
4. 缓存机制

## 安全考虑

1. **消息验证** - 所有消息都包含message_id进行验证
2. **状态检查** - 严格的状态转换验证
3. **故障隔离** - 故障不会影响其他充电点
4. **数据完整性** - 使用事务确保数据一致性

## 监控和日志

系统使用统一的日志系统，支持不同级别的日志记录：
- DEBUG - 调试信息
- INFO - 一般信息
- WARNING - 警告信息
- ERROR - 错误信息

所有关键操作都有日志记录，便于问题排查和系统监控。
