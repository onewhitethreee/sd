# Kafka 迁移快速开始指南

> **当前进度**: 阶段 1 - Engine → Central 数据流
> **状态**: ✅ 完成
> **完成度**: 100%

---

## 📋 已完成的工作

### ✅ 阶段 0: 准备工作
- [x] 完善 KafkaManager
  - [x] 添加 `produce_message()` 方法（支持重试）
  - [x] 添加 `subscribe_topic()` 便捷方法
  - [x] 添加 `create_topic_if_not_exists()` 方法
  - [x] 添加 `health_check()` 方法

### ✅ 阶段 1: Engine → Central 数据流（100%）
- [x] Engine 启用 Kafka Producer
  - [x] 取消注释 `_init_kafka()` 调用
  - [x] 完善 `_init_kafka()` 方法，添加 topic 创建
- [x] Engine 发送充电数据到 Kafka
  - [x] 改进 `_send_charging_data()` 方法，添加 timestamp 和错误处理
  - [x] 改进 `_send_charging_completion()` 方法，添加 timestamp 和错误处理
- [x] Central 启用 Kafka Consumer
  - [x] 在 `initialize_systems()` 中启用 Kafka 初始化
  - [x] 完善 `_init_kafka_consumer()` 方法，订阅 Engine 的 topics
  - [x] 添加 `_handle_charging_data_from_kafka()` 回调方法
  - [x] 添加 `_handle_charging_complete_from_kafka()` 回调方法
- [x] Central 添加幂等性处理
  - [x] 在 MessageDispatcher 中添加 `_processed_message_ids` 集合
  - [x] 添加 `_is_duplicate_message()` 方法
  - [x] 在 `_handle_charging_data_message()` 中添加幂等性检查
  - [x] 在 `_handle_charge_completion_message()` 中添加幂等性检查
- [ ] 测试 Engine → Central 数据流

---

## 🚀 快速开始

### 1. 启动 Kafka

#### 方式 1: 使用 Docker Compose（推荐）

检查是否有 `docker-compose.yml` 文件：

```bash
# 查看 docker-compose.yml
cat docker-compose.yml
```

如果存在，启动 Kafka：

```bash
# 启动 Kafka 和 Zookeeper
docker-compose up -d

# 查看日志
docker-compose logs -f kafka

# 检查 Kafka 是否运行
docker ps | grep kafka
```

#### 方式 2: 手动启动（如果没有 docker-compose.yml）

创建 `docker-compose.yml` 文件：

```yaml
version: '3'
services:
  zookeeper:
    image: wurstmeister/zookeeper
    ports:
      - "2181:2181"
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: wurstmeister/kafka
    ports:
      - "9092:9092"
    environment:
      KAFKA_ADVERTISED_HOST_NAME: localhost
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: 'true'
      KAFKA_DELETE_TOPIC_ENABLE: 'true'
    depends_on:
      - zookeeper
```

然后启动：

```bash
docker-compose up -d
```

### 2. 验证 Kafka 已启动

```bash
# 检查 Kafka 端口
netstat -an | findstr 9092  # Windows
# 或
lsof -i :9092  # Linux/Mac

# 使用 Kafka 命令行工具测试
docker exec -it <kafka_container_id> kafka-topics.sh --list --bootstrap-server localhost:9092
```

---

## 📝 下一步：Central 启用 Kafka Consumer

### 当前任务：Central 消费来自 Engine 的 Kafka 消息

现在 Engine 已经能够发送消息到 Kafka，下一步是让 Central 消费这些消息。

**文件**: `Core/Central/EV_Central.py`

**步骤 1: 启用 Kafka Consumer 初始化**

在 `EV_Central.py` 中找到 `_init_kafka_consumer()` 调用（应该在 `__init__` 或 `initialize_system` 方法中），取消注释或确保它被调用。

**步骤 2: 订阅 Kafka Topics**

修改 `_init_kafka_consumer()` 方法：

```python
def _init_kafka_consumer(self):
    """初始化Kafka消费者"""
    if not self.kafka_manager:
        self.logger.warning("Kafka manager not initialized, cannot create consumer")
        return False

    try:
        # 订阅充电数据主题
        success1 = self.kafka_manager.subscribe_topic(
            KafkaTopics.CHARGING_SESSION_DATA,
            self._handle_charging_data_from_kafka,
            group_id="central_charging_data_group"
        )

        # 订阅充电完成主题
        success2 = self.kafka_manager.subscribe_topic(
            KafkaTopics.CHARGING_SESSION_COMPLETE,
            self._handle_charging_complete_from_kafka,
            group_id="central_charging_complete_group"
        )

        if success1 and success2:
            self.logger.info("Kafka consumers initialized successfully")
            return True
        else:
            self.logger.error("Failed to initialize some Kafka consumers")
            return False

    except Exception as e:
        self.logger.error(f"Failed to initialize Kafka consumers: {e}")
        return False
```

**步骤 3: 添加消息处理回调**

在 `EV_Central.py` 中添加两个新方法：

```python
def _handle_charging_data_from_kafka(self, message):
    """处理来自Kafka的充电数据"""
    try:
        self.logger.debug(f"Received charging data from Kafka: {message}")

        # 委托给 MessageDispatcher 处理
        if self.message_dispatcher:
            self.message_dispatcher.dispatch_message("Kafka", message)
    except Exception as e:
        self.logger.error(f"Error handling charging data from Kafka: {e}")

def _handle_charging_complete_from_kafka(self, message):
    """处理来自Kafka的充电完成消息"""
    try:
        self.logger.info(f"Received charging completion from Kafka: {message}")

        # 委托给 MessageDispatcher 处理
        if self.message_dispatcher:
            self.message_dispatcher.dispatch_message("Kafka", message)
    except Exception as e:
        self.logger.error(f"Error handling charging completion from Kafka: {e}")
```

**关键点**:
1. ✅ 使用 `subscribe_topic()` 订阅主题
2. ✅ 为每个 topic 指定不同的 consumer group
3. ✅ 消息处理委托给 MessageDispatcher，保持代码结构统一
4. ✅ 添加异常处理，避免单个消息错误导致消费者崩溃

---

## 🧪 测试步骤

### 测试 1: 验证 Engine 能连接 Kafka

```bash
# 1. 启动 Kafka（如果还没启动）
docker-compose up -d

# 2. 启动 Engine
cd Charging_point/Engine
export ENGINE_LISTEN_PORT=5001
python EV_CP_E.py localhost:9092

# 预期日志：
# ✅ "Kafka producer initialized successfully"
# ✅ "Topic charging_session_data created successfully"
# ✅ "Topic charging_session_complete created successfully"
```

### 测试 2: 监控 Kafka Topics

在另一个终端监控 Kafka 消息：

```bash
# 监控充电数据 topic
docker exec -it <kafka_container_id> kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic charging_session_data \
  --from-beginning

# 预期：当 Engine 开始充电时，应该看到类似以下的消息：
# {
#   "type": "charging_data",
#   "message_id": "uuid-1234",
#   "cp_id": "cp_001",
#   "session_id": "S001",
#   "energy_consumed_kwh": 0.003,
#   "total_cost": 0.00,
#   "charging_rate": 11.0,
#   "timestamp": 1699000000
# }
```

### 测试 3: 完整流程测试

```bash
# 终端 1: 启动 Central
cd Core/Central
python EV_Central.py 6001 localhost:9092

# 终端 2: 启动 Monitor
cd Charging_point/Monitor
python EC_CP_M.py localhost:5001 localhost:6001 cp_001

# 终端 3: 启动 Engine
cd Charging_point/Engine
export ENGINE_LISTEN_PORT=5001
python EV_CP_E.py localhost:9092

# 终端 4: 启动 Driver
cd Driver
python EV_Driver.py localhost:9092 driver_001

# 终端 5: 监控 Kafka 消息
docker exec -it <kafka_container_id> kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic charging_session_data \
  --from-beginning
```

**操作**:
1. 在 Driver 终端，输入 `list` 查看可用充电桩
2. 输入 `charge <cp_id>` 开始充电
3. 观察 Kafka 监控终端，应该每秒看到一条充电数据消息

---

## 🐛 故障排查

### 问题 1: Kafka 连接失败

**错误**: `Kafka producer初始化失败: NoBrokersAvailable`

**解决**:
1. 检查 Kafka 是否启动: `docker ps | grep kafka`
2. 检查端口是否监听: `netstat -an | findstr 9092`
3. 检查 broker 地址是否正确: 应该是 `localhost:9092`

### 问题 2: Topic 创建失败

**错误**: `Failed to create topic charging_session_data`

**解决**:
1. 手动创建 topic:
   ```bash
   docker exec -it <kafka_container_id> kafka-topics.sh \
     --create \
     --bootstrap-server localhost:9092 \
     --topic charging_session_data \
     --partitions 3 \
     --replication-factor 1
   ```

2. 检查 topic 是否存在:
   ```bash
   docker exec -it <kafka_container_id> kafka-topics.sh \
     --list \
     --bootstrap-server localhost:9092
   ```

### 问题 3: Engine 没有发送消息到 Kafka

**检查点**:
1. Kafka 是否初始化成功？查看日志中是否有 "Kafka producer initialized successfully"
2. `kafka_manager.is_connected()` 返回 True 吗？
3. `produce_message()` 是否返回 True？

**调试**:
在 `_send_charging_data()` 方法中添加更多日志：

```python
self.logger.info(f"Kafka manager: {self.kafka_manager}")
self.logger.info(f"Kafka connected: {self.kafka_manager.is_connected() if self.kafka_manager else False}")
```

---

## 📊 进度追踪

### 阶段 1 任务清单

- [x] 完善 KafkaManager
- [x] Engine 启用 Kafka Producer
- [x] Engine 发送充电数据到 Kafka
- [ ] **当前**: Central 启用 Kafka Consumer
- [ ] Central 添加幂等性处理
- [ ] 测试 Engine → Central 数据流

### 预计时间

- 阶段 1 完成: 2-3 天
- 阶段 2 开始: 3-4 天后
- 完整迁移: 2-3 周

---

## 🔗 相关文档

- [项目架构分析与Kafka迁移指南](./项目架构分析与Kafka迁移指南.md) - 完整迁移方案
- [Kafka集成架构说明](./Kafka集成架构说明.md) - 详细的技术说明
- [严重问题修复总结](./严重问题修复总结.md) - P0 问题修复记录

---

**更新日期**: 2025-11-01
**当前进度**: 阶段 1 (50%)
**下一步**: Central 启用 Kafka Consumer → 添加幂等性处理
