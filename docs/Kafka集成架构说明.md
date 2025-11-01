# Kafka 集成架构说明文档

## 目录
1. [概述](#概述)
2. [当前架构 vs Kafka架构](#当前架构-vs-kafka架构)
3. [Kafka的优势与局限性](#kafka的优势与局限性)
4. [混合架构设计方案](#混合架构设计方案)
5. [必须保留的重试机制](#必须保留的重试机制)
6. [迁移步骤建议](#迁移步骤建议)
7. [配置示例](#配置示例)
8. [测试策略](#测试策略)

---

## 概述

本文档说明在充电站管理系统中引入 Kafka 消息队列后的架构变化、需要保留的重试机制，以及具体的集成步骤。

### 核心结论

**引入 Kafka 后，现有的重试机制仍然重要，但作用范围会发生变化。**

Kafka 提供了消息传输层的可靠性保障，但无法替代应用层的连接管理和业务逻辑处理。

---

## 当前架构 vs Kafka架构

### 当前架构（纯 Socket 通信）

```
┌──────────┐                    ┌─────────────┐
│  Driver  │◄──────Socket──────►│   Central   │
└──────────┘                    └─────────────┘
                                       │
                                    Socket
                                       │
┌──────────┐                    ┌─────────────┐
│  Engine  │◄──────Socket──────►│   Monitor   │
└──────────┘                    └─────────────┘
```

**特点：**
- ✅ 请求-响应同步，延迟低
- ✅ 实现简单直接
- ❌ 消息不持久化，连接断开消息丢失
- ❌ 扩展性差，增加客户端需要更多连接
- ❌ 没有消息队列缓冲

### Kafka 混合架构（推荐）

```
                    ┌────────────────┐
                    │  Kafka Broker  │
                    └────────────────┘
                       ▲          ▲
                       │          │
            (Driver    │          │    (Engine
             命令/状态) │          │     充电数据)
                       │          │
┌──────────┐      ┌───┴──────────┴───┐      ┌──────────┐
│  Driver  │─────►│     Central      │◄────►│  Monitor │
└──────────┘      └──────────────────┘      └──────────┘
   (Kafka)           (Kafka + Socket)          (Socket)
                            │
                         Socket
                      (控制命令)
                            │
                      ┌─────┴─────┐
                      │   Engine  │
                      └───────────┘
```

**通信方式：**
- **Driver ↔ Central**：Kafka（异步消息队列）
- **Central ↔ Monitor**：Socket（实时控制命令）
- **Monitor ↔ Engine**：Socket（实时充电控制）
- **Engine → Central**：Kafka（充电数据上报）

**特点：**
- ✅ Driver 与 Central 解耦，支持多 Driver 并发
- ✅ Engine 充电数据通过 Kafka 持久化，不会丢失
- ✅ Monitor 与 Central/Engine 保持 Socket 低延迟控制
- ✅ 支持 Central 横向扩展（多实例消费 Kafka）
- ⚠️ 架构稍复杂，需要维护 Kafka 集群

---

## Kafka的优势与局限性

### Kafka 提供的能力（可以替代的部分）

#### 1. 消息持久化
```python
# 当前：消息通过 Socket 发送，如果接收方断线就丢失
client_socket.send(message)  # 如果对方断线，消息丢失

# Kafka：消息保存在磁盘，消费者恢复后可以继续消费
kafka_producer.send('charging_data', message)  # 消息持久化
```

#### 2. At-least-once 交付保证
```python
# Kafka配置（已在 KafkaManager.py 中）
self.producer = KafkaProducer(
    acks="all",  # 等待所有副本确认
    retries=3,   # 自动重试3次
)
```

#### 3. 消费者组和负载均衡
```python
# 多个 Central 实例可以组成消费者组，分担负载
consumer = KafkaConsumer(
    'charging_data',
    group_id='central_group',  # 消息自动分配给组内成员
)
```

#### 4. Offset 管理
```python
# 消费者可以从上次中断的位置继续消费
# 不需要手动跟踪"哪些消息已处理"
```

### Kafka 无法提供的能力（必须保留的部分）

#### 1. 客户端连接管理

**问题：** Kafka 不会主动告诉你某个生产者/消费者断线了。

**示例场景：**
```python
# Driver.py - 如果与 Kafka 的连接断开
# Kafka 不会自动重连你的应用程序

# ✅ 必须保留的代码
def _reconnect_loop(self):
    """自动重连循环"""
    while self.running and not self._is_connected:
        try:
            if self._connect_to_kafka():  # 你需要实现重连逻辑
                self._handle_reconnection_success()
                break
        except Exception as e:
            self.logger.error(f"Kafka重连失败: {e}")
        time.sleep(self.RECONNECT_INTERVAL)
```

#### 2. 业务逻辑和状态管理

**问题：** Kafka 只负责传输消息，不理解你的业务规则。

**示例场景：**
```python
# MessageDispatcher.py
# 当 Driver 断开连接时，必须停止正在进行的充电会话

# ✅ 必须保留的代码
def handle_driver_disconnect(self, client_id):
    """处理Driver断开连接"""
    active_sessions = self._driver_active_sessions.get(driver_id, [])
    if active_sessions:
        for session_id in active_sessions.copy():
            # 这是业务逻辑，Kafka 无法自动处理
            self._stop_session_due_to_driver_disconnect(session_id, driver_id)
```

**为什么 Kafka 不能做？**
- Kafka 不知道"Driver 断线意味着要停止充电"
- Kafka 只知道"这个消费者不再拉取消息了"

#### 3. 实时请求-响应

**问题：** Kafka 是异步的，不适合需要立即响应的场景。

**示例场景：**
```python
# Driver 请求可用充电桩列表
request = {"type": "available_cps_request", "driver_id": "D001"}

# Socket 模式：立即得到响应
response = send_and_wait(request)  # 100ms 内返回
print(response["charging_points"])

# Kafka 模式：需要等待 Central 从 topic 读取、处理、发布到另一个 topic
# 延迟可能达到 500ms-2s，用户体验差
```

#### 4. 客户端活跃检测

**问题：** Kafka 的 heartbeat 是消费者与 broker 之间的，不是你的应用组件之间的。

**示例场景：**
```python
# Monitor 需要知道 Central 是否在线
# Kafka 不会告诉你"Central 没有从 topic 消费消息了"

# ✅ 必须保留的代码
def _handle_central_disconnection(self):
    """处理Central断开连接"""
    if self._current_status == Status.CHARGING.value:
        self.logger.warning("Central断线，停止充电防止数据丢失")
        self._send_stop_command_to_engine()
```

---

## 混合架构设计方案

### 方案：控制层用 Socket，业务层用 Kafka

| 通信类型 | 使用技术 | 原因 |
|---------|---------|------|
| Driver ↔ Central (查询充电桩、开始充电、停止充电) | **Kafka** | 支持多 Driver 并发，消息持久化 |
| Central ↔ Monitor (注册、状态更新、控制命令) | **Socket** | 实时控制命令，低延迟 |
| Monitor ↔ Engine (启动/停止充电命令) | **Socket** | 实时控制，不能有延迟 |
| Engine → Central (充电数据) | **Kafka** | 大量数据流，持久化存储 |
| Central → Driver (充电状态更新) | **Kafka** | 异步推送，解耦 |

### 详细架构图

```
┌──────────────────────────────────────────────────────────────┐
│                         Driver                               │
│  ┌──────────────┐              ┌──────────────┐             │
│  │Kafka Producer│──Requests───►│Kafka Consumer│             │
│  │              │◄─Responses───│              │             │
│  └──────────────┘              └──────────────┘             │
└────────┬────────────────────────────────┬───────────────────┘
         │ (Kafka)                        │ (Kafka)
         │ driver_requests                │ driver_responses_D001
         ▼                                │
┌────────────────────────────────────────┴──────────────────────┐
│                        Central                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │    Kafka     │  │    Kafka     │  │    Socket    │       │
│  │   Consumer   │  │   Producer   │  │    Server    │       │
│  │(driver_req)  │  │(driver_resp) │  │  (Monitor)   │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                              │                │
│  ┌──────────────┐                            │                │
│  │    Kafka     │◄───充电数据────────────────┘                │
│  │   Consumer   │                                             │
│  │(charging_data)                                             │
│  └──────────────┘                                             │
└──────────────────────────┬───────────────────────────────────┘
                           │ Socket (控制命令)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                        Monitor                               │
│  ┌──────────────┐              ┌──────────────┐             │
│  │Socket Client │              │Socket Server │             │
│  │  (Central)   │              │   (Engine)   │             │
│  └──────────────┘              └──────────────┘             │
└───────────────────────────────────────┬──────────────────────┘
                                        │ Socket (控制)
                                        ▼
┌──────────────────────────────────────────────────────────────┐
│                        Engine                                │
│  ┌──────────────┐              ┌──────────────┐             │
│  │Socket Client │              │    Kafka     │             │
│  │  (Monitor)   │              │   Producer   │             │
│  └──────────────┘              │(charging_data)│             │
│                                └──────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

### Kafka Topics 设计

根据新架构，重新设计 Topics：

```python
# Driver 相关（Driver ↔ Central 通过 Kafka）
DRIVER_REQUESTS = "driver_requests"                    # Driver → Central
DRIVER_RESPONSES_{driver_id} = "driver_responses_D001" # Central → 特定 Driver
  # 包含：available_cps_request, charge_request, stop_charging_request

# 充电数据流（Engine → Central 通过 Kafka）
CHARGING_SESSION_DATA = "charging_session_data"        # Engine → Central
CHARGING_SESSION_COMPLETE = "charging_session_complete" # Engine → Central
CHARGING_STATUS_UPDATES = "charging_status_updates"    # Central → Driver
  # Central 处理后推送给 Driver

# 系统事件（可选）
SYSTEM_ALERTS = "system_alerts"                        # 任意组件 → Central
```

**注意：Monitor 相关的所有通信保持 Socket，不使用 Kafka**

---

## 必须保留的重试机制

### 1. Driver 的 Kafka 连接重试 ✅

**位置：** `Driver/EV_Driver.py`

**当前代码（Socket 版）：**
```python
# Driver/EV_Driver.py:212-242
def _reconnect_loop(self):
    """自动重连循环"""
    attempt = 0
    while self.running and not self._is_connected:
        attempt += 1
        self.logger.info(f"尝试重连到 Central (第 {attempt} 次)...")

        try:
            if self._connect_to_central():  # 当前是 Socket
                self.logger.info("✅ 成功重连到 Central!")
                self._handle_reconnection_success()
                break
        except Exception as e:
            self.logger.error(f"重连失败: {e}")

        time.sleep(self.RECONNECT_INTERVAL)
```

**为什么保留：**
- Driver 改用 Kafka 后，仍需要连接到 Kafka broker
- Kafka 客户端可能因网络问题断开连接
- 需要应用层实现自动重连机制

**迁移后版本（Kafka 版）：**
```python
def _reconnect_to_kafka(self):
    """重连到 Kafka（Driver 版）"""
    attempt = 0
    while self.running and not self._kafka_connected:
        attempt += 1
        self.logger.info(f"尝试重连到 Kafka Broker (第 {attempt} 次)...")

        try:
            # 重新初始化 Kafka 生产者和消费者
            self.kafka_manager.init_producer()

            # 重新订阅 driver 响应 topic
            response_topic = f"driver_responses_{self.driver_id}"
            self.kafka_manager.subscribe_topic(
                response_topic,
                self._handle_central_response
            )

            self._kafka_connected = True
            self.logger.info("✅ 成功重连到 Kafka!")
            break

        except Exception as e:
            self.logger.error(f"Kafka重连失败: {e}")
            time.sleep(self.RECONNECT_INTERVAL)
```

---

### 2. 业务逻辑层重试 ✅

**位置：** `Core/Central/MessageDispatcher.py`

**代码示例：**
```python
# Core/Central/MessageDispatcher.py
def handle_driver_disconnect(self, client_id):
    """处理Driver断开连接"""
    driver_id = self._client_to_driver.get(client_id)
    if not driver_id:
        return None

    # 停止该Driver的所有活跃充电会话
    active_sessions = self._driver_active_sessions.get(driver_id, [])
    if active_sessions:
        for session_id in active_sessions.copy():
            self._stop_session_due_to_driver_disconnect(session_id, driver_id)

    # 清理连接映射
    self._cleanup_driver_mappings(driver_id, client_id)
```

**为什么保留：**
- 这是业务逻辑，不是网络层问题
- Kafka 不知道"Driver 断线 = 停止充电会话"这个规则
- 必须由应用层监控并执行

**迁移后调整：**
```python
def handle_driver_disconnect(self, driver_id):
    """处理Driver断开连接（Kafka版）"""
    # 检查该 Driver 是否还在发送心跳
    last_heartbeat = self._driver_heartbeats.get(driver_id)
    if last_heartbeat and (time.time() - last_heartbeat > 30):
        self.logger.warning(f"Driver {driver_id} 心跳超时，视为断线")

        # 停止活跃会话（逻辑不变）
        active_sessions = self._driver_active_sessions.get(driver_id, [])
        for session_id in active_sessions.copy():
            self._stop_session_due_to_driver_disconnect(session_id, driver_id)
```

---

### 3. Monitor 的 Socket 连接管理 ✅

**位置：** `Charging_point/Monitor/EC_CP_M.py`

**代码示例：**
```python
# Charging_point/Monitor/EC_CP_M.py
def _check_and_update_to_active(self):
    """检查是否满足ACTIVE状态的条件"""
    if (
        self.central_conn_mgr and self.central_conn_mgr.is_connected
        and self.engine_conn_mgr and self.engine_conn_mgr.is_connected
    ):
        if self._current_status != Status.ACTIVE.value:
            self.update_cp_status(Status.ACTIVE.value)

def _handle_central_disconnection(self):
    """处理Central断开连接"""
    if self._current_status == Status.CHARGING.value:
        self.logger.warning("Central断线，停止充电防止数据丢失")
        self._send_stop_command_to_engine()
    self.update_cp_status(Status.FAULTY.value)
```

**为什么保留：**
- Monitor 与 Central/Engine 使用 **Socket 通信（不改变）**
- 这些重连逻辑完全保留，不需要修改
- Monitor 不使用 Kafka，所以现有的 Socket 重连机制继续有效

**迁移后：无需调整（Monitor 保持 Socket 通信）**

---

### 4. 幂等性处理（新增） ⚠️

**为什么需要：**
Kafka 保证 **at-least-once** 交付，意味着消息可能重复。

**示例场景：**
```python
# 场景：Engine 发送充电完成消息
message = {
    "type": "charge_completion",
    "session_id": "S001",
    "energy_kwh": 50.0,
}
kafka_producer.send("charging_session_complete", message)

# Kafka 可能因为网络问题重试，导致 Central 收到两次
# 如果不处理幂等性，会重复扣费！
```

**解决方案：**
```python
# Core/Central/MessageDispatcher.py（新增）
def _handle_charge_completion_kafka(self, message):
    """处理充电完成消息（幂等版本）"""
    session_id = message.get("session_id")

    # 检查是否已经处理过
    if session_id in self._processed_sessions:
        self.logger.warning(f"会话 {session_id} 已处理，忽略重复消息")
        return

    # 正常处理
    self._process_charge_completion(message)

    # 标记已处理
    self._processed_sessions.add(session_id)

    # 定期清理旧记录（避免内存泄漏）
    self._cleanup_old_processed_sessions()
```

---

### 5. Correlation ID 跟踪（新增） ⚠️

**为什么需要：**
Kafka 是异步的，需要关联请求和响应。

**示例场景：**
```python
# Driver 发起充电请求
request_id = str(uuid.uuid4())
request = {
    "type": "start_charging_request",
    "correlation_id": request_id,  # 关联ID
    "driver_id": "D001",
    "cp_id": "CP001",
}
kafka_producer.send("charging_commands", request)

# Central 处理后发布响应
response = {
    "type": "start_charging_response",
    "correlation_id": request_id,  # 使用相同的ID
    "status": "success",
    "session_id": "S123",
}
kafka_producer.send("charging_responses", response)

# Driver 的消费者根据 correlation_id 匹配响应
```

**实现示例：**
```python
# Driver/EV_Driver.py（新增）
class Driver:
    def __init__(self):
        self._pending_requests = {}  # {correlation_id: Future}

    def request_start_charging_async(self, cp_id):
        """异步请求开始充电"""
        correlation_id = str(uuid.uuid4())
        future = asyncio.Future()

        # 记录待处理请求
        self._pending_requests[correlation_id] = future

        # 发送请求
        request = {
            "correlation_id": correlation_id,
            "driver_id": self.driver_id,
            "cp_id": cp_id,
        }
        self.kafka_producer.send("charging_commands", request)

        # 设置超时
        asyncio.wait_for(future, timeout=30.0)
        return future

    def _handle_charging_response(self, message):
        """处理充电响应"""
        correlation_id = message.get("correlation_id")
        future = self._pending_requests.pop(correlation_id, None)

        if future:
            future.set_result(message)  # 完成 Future
        else:
            self.logger.warning(f"收到未知的响应: {correlation_id}")
```

---

## 迁移步骤建议

### 阶段 1：准备阶段（1-2周）

#### 1.1 搭建 Kafka 环境
```bash
# Docker Compose 方式
version: '3'
services:
  zookeeper:
    image: wurstmeister/zookeeper
    ports:
      - "2181:2181"

  kafka:
    image: wurstmeister/kafka
    ports:
      - "9092:9092"
    environment:
      KAFKA_ADVERTISED_HOST_NAME: localhost
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_CREATE_TOPICS: "charging_point_heartbeat:1:1,charging_session_data:1:1"
```

#### 1.2 验证现有 KafkaManager
```python
# 测试脚本
from Common.Queue.KafkaManager import KafkaManager

manager = KafkaManager("localhost:9092")
manager.init_producer()

# 测试发送
manager.send_message("test_topic", {"msg": "Hello Kafka"})

# 测试消费
def callback(message):
    print(f"收到消息: {message}")

manager.subscribe_topic("test_topic", callback)
```

### 阶段 2：迁移 Engine 充电数据上报（2-3周）

优先迁移数据流，保持控制流不变。

#### 2.1 Engine 添加 Kafka Producer

**Engine 初始化：**
```python
# Engine/EV_CP_E.py
class Engine:
    def __init__(self, args):
        # ... 现有代码 ...

        # 新增：初始化 Kafka
        self.kafka_manager = KafkaManager(
            broker_address="localhost:9092",
            logger=self.logger
        )
        self.kafka_manager.init_producer()
        self.logger.info("Engine Kafka Producer 已初始化")
```

#### 2.2 充电数据通过 Kafka 发送

**当前（通过 Socket 发给 Monitor）：**
```python
# Engine/EngineMessageDispatcher.py
def _send_charging_data_to_monitor(self, data):
    message = {
        "type": "charging_data_update",
        "session_id": data["session_id"],
        "energy_kwh": data["energy_consumed_kwh"],
        # ...
    }
    self.engine.monitor_client.send(message)  # 发给 Monitor
```

**迁移后（直接通过 Kafka 发给 Central）：**
```python
# Engine/EngineMessageDispatcher.py
def _send_charging_data_to_central(self, data):
    kafka_message = {
        "type": "charging_data_update",
        "session_id": data.get("session_id"),
        "cp_id": self.engine.cp_id,
        "energy_kwh": data.get("energy_consumed_kwh"),
        "current": data.get("current"),
        "voltage": data.get("voltage"),
        "timestamp": int(time.time()),
    }

    # 直接发送到 Kafka
    self.engine.kafka_manager.send_message(
        "charging_session_data",
        kafka_message
    )
```

#### 2.3 Central 消费充电数据

**Central 初始化 Kafka Consumer：**
```python
# Central/EV_Central.py
def _init_kafka_consumers(self):
    """初始化 Kafka 消费者"""

    # 消费充电数据
    def charging_data_callback(message):
        session_id = message.get("session_id")
        cp_id = message.get("cp_id")

        # 转发给对应的 Driver
        self.message_dispatcher._handle_charging_data_from_engine(message)

    self.kafka_manager.subscribe_topic(
        "charging_session_data",
        charging_data_callback
    )

    self.logger.info("Kafka consumers initialized")
```

### 阶段 3：迁移 Driver ↔ Central 通信（3-4周）

**这是最关键的迁移，需要实现异步请求-响应模式。**

#### 3.1 Driver 初始化 Kafka

```python
# Driver/EV_Driver.py
class Driver:
    def __init__(self, args):
        # ... 现有代码 ...

        # 替换 Socket 为 Kafka
        self.driver_id = args.id_client
        self.kafka_manager = KafkaManager(
            broker_address="localhost:9092",
            logger=self.logger
        )
        self.kafka_manager.init_producer()

        # 订阅自己的响应 topic
        response_topic = f"driver_responses_{self.driver_id}"
        self.kafka_manager.subscribe_topic(
            response_topic,
            self._handle_central_response
        )

        # Correlation ID 跟踪
        self._pending_requests = {}  # {correlation_id: callback}
        self._pending_lock = threading.Lock()

        self.logger.info(f"Driver Kafka initialized, response topic: {response_topic}")
```

#### 3.2 实现异步请求机制

```python
# Driver/EV_Driver.py
def _send_kafka_request(self, message_type, timeout=30, **kwargs):
    """
    通过 Kafka 发送请求并等待响应

    Args:
        message_type: 消息类型
        timeout: 超时时间（秒）
        **kwargs: 消息字段

    Returns:
        响应消息，如果超时返回 None
    """
    correlation_id = str(uuid.uuid4())
    request = {
        "type": message_type,
        "correlation_id": correlation_id,
        "driver_id": self.driver_id,
        "timestamp": int(time.time()),
        **kwargs
    }

    # 创建 Event 用于等待响应
    response_event = threading.Event()
    response_data = {"result": None}

    def callback(response):
        response_data["result"] = response
        response_event.set()

    # 注册回调
    with self._pending_lock:
        self._pending_requests[correlation_id] = callback

    # 发送请求到 Kafka
    self.kafka_manager.send_message("driver_requests", request)

    # 等待响应
    if response_event.wait(timeout=timeout):
        return response_data["result"]
    else:
        self.logger.error(f"Request {message_type} timed out")
        with self._pending_lock:
            self._pending_requests.pop(correlation_id, None)
        return None

def _handle_central_response(self, message):
    """处理来自 Central 的响应"""
    correlation_id = message.get("correlation_id")

    with self._pending_lock:
        callback = self._pending_requests.pop(correlation_id, None)

    if callback:
        callback(message)
    else:
        self.logger.warning(f"Received response for unknown request: {correlation_id}")
```

#### 3.3 修改业务方法使用 Kafka

```python
# Driver/EV_Driver.py
def request_available_charging_points(self):
    """请求可用充电桩列表（Kafka 版）"""
    response = self._send_kafka_request(
        "available_cps_request",
        timeout=10
    )

    if response and response.get("status") == "success":
        return response.get("charging_points", [])
    else:
        self.logger.error("Failed to get available charging points")
        return []

def start_charging(self, cp_id):
    """开始充电（Kafka 版）"""
    response = self._send_kafka_request(
        "charge_request",
        cp_id=cp_id,
        timeout=15
    )

    if response and response.get("status") == "success":
        session_id = response.get("session_id")
        self.current_charging_session = {
            "session_id": session_id,
            "cp_id": cp_id,
        }
        return session_id
    else:
        self.logger.error(f"Failed to start charging at {cp_id}")
        return None
```

#### 3.4 Central 处理 Driver 请求

```python
# Central/EV_Central.py
def _init_kafka_consumers(self):
    """初始化 Kafka 消费者"""

    # ... 之前的充电数据消费 ...

    # 消费 Driver 请求
    def driver_request_callback(message):
        message_type = message.get("type")
        correlation_id = message.get("correlation_id")
        driver_id = message.get("driver_id")

        # 处理请求
        response = self.message_dispatcher.handle_driver_request_kafka(message)

        # 发送响应到 Driver 的专属 topic
        if response:
            response["correlation_id"] = correlation_id
            response_topic = f"driver_responses_{driver_id}"
            self.kafka_manager.send_message(response_topic, response)

    self.kafka_manager.subscribe_topic(
        "driver_requests",
        driver_request_callback
    )
```

#### 3.5 MessageDispatcher 处理请求

```python
# Central/MessageDispatcher.py
def handle_driver_request_kafka(self, message):
    """处理来自 Kafka 的 Driver 请求"""
    message_type = message.get("type")
    driver_id = message.get("driver_id")

    # 路由到具体的处理函数
    if message_type == "available_cps_request":
        return self._handle_available_cps_request_kafka(message)
    elif message_type == "charge_request":
        return self._handle_charge_request_kafka(message)
    elif message_type == "stop_charging_request":
        return self._handle_stop_charging_request_kafka(message)
    else:
        return {
            "type": f"{message_type}_response",
            "status": "error",
            "info": f"Unknown request type: {message_type}"
        }

def _handle_available_cps_request_kafka(self, message):
    """处理查询可用充电桩请求（Kafka 版）"""
    charging_points = self.charging_point_manager.get_available_charging_points()

    return {
        "type": "available_cps_response",
        "status": "success",
        "charging_points": charging_points,
    }
```

### 阶段 4：测试与优化（2周）

#### 4.1 故障场景测试

| 测试场景 | 预期行为 | 验证方法 |
|---------|---------|---------|
| Kafka broker 宕机 | 客户端自动重连，消息不丢失 | 停止 Kafka，重启后检查消息 |
| Central 宕机 | Monitor 停止充电，Driver 收到通知 | 杀死 Central 进程，观察日志 |
| Driver 断线 | Central 停止充电会话 | 模拟网络中断 |
| 消息重复 | 幂等性处理，不重复扣费 | 手动发送重复消息 |
| 高负载 | Kafka 缓冲消息，消费者稳定处理 | 模拟1000个心跳/秒 |

#### 4.2 性能基准测试

```python
# test/benchmark_kafka_vs_socket.py
import time
from Common.Queue.KafkaManager import KafkaManager

def benchmark_kafka():
    manager = KafkaManager("localhost:9092")
    manager.init_producer()

    start = time.time()
    for i in range(1000):
        manager.send_message("test", {"id": i})
    end = time.time()

    print(f"Kafka: {end - start:.2f}秒发送1000条消息")

def benchmark_socket():
    # 类似测试 Socket
    pass
```

### 阶段 5：监控与告警（持续）

#### 5.1 添加 Kafka 监控

```python
# Common/Queue/KafkaMonitor.py（新增）
from kafka.admin import KafkaAdminClient

class KafkaMonitor:
    def __init__(self, broker_address):
        self.admin = KafkaAdminClient(bootstrap_servers=[broker_address])

    def check_topic_lag(self, topic, group_id):
        """检查消费滞后"""
        consumer_offsets = self.admin.list_consumer_group_offsets(group_id)
        # 计算 lag
        lag = self._calculate_lag(consumer_offsets)

        if lag > 1000:
            self.logger.warning(f"Topic {topic} 消费滞后: {lag}条消息")
```

#### 5.2 告警规则

```yaml
# alerts.yaml
rules:
  - name: kafka_consumer_lag_high
    condition: consumer_lag > 1000
    action: send_email
    message: "Kafka消费者滞后过高"

  - name: kafka_broker_down
    condition: broker_count < 1
    action: send_sms
    message: "Kafka broker 宕机"
```

---

## 配置示例

### Kafka Producer 配置

```python
# Common/Queue/KafkaManager.py（优化版）
class KafkaManager:
    def init_producer(self, profile="default"):
        """
        初始化生产者，支持不同的配置档案

        Args:
            profile: 配置档案名称
                - "default": 平衡性能和可靠性
                - "high_throughput": 高吞吐量，可能丢消息
                - "high_reliability": 高可靠性，性能较低
        """
        configs = {
            "default": {
                "acks": "all",
                "retries": 3,
                "max_in_flight_requests_per_connection": 5,
                "compression_type": "snappy",
            },
            "high_throughput": {
                "acks": "1",
                "retries": 0,
                "max_in_flight_requests_per_connection": 10,
                "compression_type": "lz4",
                "batch_size": 32768,
                "linger_ms": 10,
            },
            "high_reliability": {
                "acks": "all",
                "retries": 10,
                "max_in_flight_requests_per_connection": 1,
                "compression_type": None,
                "enable_idempotence": True,
            },
        }

        config = configs.get(profile, configs["default"])
        self.producer = KafkaProducer(
            bootstrap_servers=[self.broker_address],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            **config
        )
```

### Kafka Consumer 配置

```python
def subscribe_topic(self, topic, callback, consumer_config=None):
    """
    订阅主题，支持自定义配置

    Args:
        topic: 主题名称
        callback: 回调函数
        consumer_config: 自定义配置
    """
    default_config = {
        "group_id": f"{topic}_group",
        "auto_offset_reset": "latest",  # 从最新消息开始
        "enable_auto_commit": True,
        "auto_commit_interval_ms": 5000,
        "max_poll_records": 100,
    }

    if consumer_config:
        default_config.update(consumer_config)

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=[self.broker_address],
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        **default_config
    )

    # 启动消费线程
    thread = threading.Thread(
        target=self._consume_loop,
        args=(consumer, callback),
        daemon=True
    )
    thread.start()
```

---

## 测试策略

### 单元测试

```python
# test/test_kafka_integration.py
import unittest
from Common.Queue.KafkaManager import KafkaManager

class TestKafkaIntegration(unittest.TestCase):
    def setUp(self):
        self.manager = KafkaManager("localhost:9092")
        self.manager.init_producer()

    def test_send_and_receive(self):
        """测试发送和接收消息"""
        received_messages = []

        def callback(msg):
            received_messages.append(msg)

        # 订阅
        self.manager.subscribe_topic("test_topic", callback)

        # 发送
        test_msg = {"id": 1, "data": "test"}
        self.manager.send_message("test_topic", test_msg)

        # 等待接收
        time.sleep(2)
        self.assertEqual(len(received_messages), 1)
        self.assertEqual(received_messages[0], test_msg)

    def test_idempotence(self):
        """测试幂等性处理"""
        # 发送重复消息
        msg = {"session_id": "S001", "energy": 50}
        self.manager.send_message("charging_data", msg)
        self.manager.send_message("charging_data", msg)  # 重复

        # 验证只处理一次
        # （需要在 Central 的 dispatcher 中实现计数器）
```

### 集成测试

```python
# test/test_driver_charging_flow_kafka.py
class TestDriverChargingFlowKafka(unittest.TestCase):
    def test_complete_charging_cycle(self):
        """测试完整充电流程（使用Kafka）"""
        # 1. Driver 请求充电桩列表
        driver = Driver(use_kafka=True)
        cps = driver.request_available_charging_points()
        self.assertGreater(len(cps), 0)

        # 2. Driver 开始充电
        session_id = driver.start_charging(cps[0]["cp_id"])
        self.assertIsNotNone(session_id)

        # 3. 等待充电数据
        time.sleep(10)
        status = driver.get_charging_status()
        self.assertGreater(status["energy_kwh"], 0)

        # 4. Driver 停止充电
        result = driver.stop_charging()
        self.assertEqual(result["status"], "success")
```

### 故障注入测试

```python
# test/test_fault_injection.py
class TestFaultInjection(unittest.TestCase):
    def test_kafka_broker_down(self):
        """测试 Kafka broker 宕机场景"""
        driver = Driver(use_kafka=True)

        # 正常发送
        driver.send_heartbeat()

        # 模拟 broker 宕机
        self._stop_kafka_broker()

        # 验证重连机制
        time.sleep(5)
        self.assertFalse(driver._is_connected)

        # 重启 broker
        self._start_kafka_broker()

        # 验证自动恢复
        time.sleep(10)
        self.assertTrue(driver._is_connected)
        driver.send_heartbeat()  # 应该成功
```

---

## 总结

### 关键要点

1. **正确的 Kafka 架构划分**
   - ✅ **Driver ↔ Central**：使用 Kafka（支持多 Driver，消息持久化）
   - ✅ **Engine → Central**：使用 Kafka（充电数据流）
   - ✅ **Central ↔ Monitor**：保持 Socket（实时控制）
   - ✅ **Monitor ↔ Engine**：保持 Socket（实时控制）

2. **重试机制仍然重要**
   - Driver 需要实现 Kafka 连接重试
   - Monitor 的 Socket 重连完全保留（不改动）
   - Driver 断线时的业务逻辑清理仍需保留
   - 新增幂等性处理和 Correlation ID 机制

3. **核心技术挑战**
   - **异步请求-响应**：Kafka 本质是异步的，需要实现 Correlation ID 跟踪
   - **超时处理**：Driver 发送请求后需要设置超时等待响应
   - **消息幂等性**：防止 Kafka 重复消息导致重复操作
   - **Driver 专属 Topic**：每个 Driver 需要独立的响应 topic

4. **迁移路径**
   1. 先迁移 Engine → Central 数据流（影响小）
   2. 再迁移 Driver ↔ Central 交互（影响大，需要仔细测试）
   3. Monitor 相关代码完全不动

### 架构优势

引入 Kafka 后的好处：

| 场景 | 当前（纯 Socket） | 迁移后（Kafka + Socket） |
|------|------------------|-------------------------|
| 多个 Driver 并发 | 每个 Driver 一个 Socket 连接 | 所有 Driver 共享 Kafka，无连接数限制 |
| Driver 离线期间的消息 | 消息丢失 | Kafka 持久化，Driver 上线后继续消费 |
| Central 横向扩展 | 困难（需要负载均衡） | 简单（多个 Central 实例组成消费者组）|
| 充电数据丢失 | Engine → Monitor → Central 链路断开会丢失 | Kafka 持久化，不会丢失 |
| Monitor 控制延迟 | 低（Socket） | 低（保持 Socket） |

### 下一步行动

- [ ] 搭建 Kafka 测试环境
- [ ] 修改 `KafkaManager.py` 支持动态 topic 创建
- [ ] 在 Driver 中实现 Correlation ID 机制
- [ ] 在 Central 中实现 Driver 请求路由
- [ ] 在 Engine 中添加 Kafka Producer
- [ ] 编写完整的集成测试
- [ ] **重要**：Monitor 相关代码不需要修改

---

## 参考资料

- [Kafka官方文档](https://kafka.apache.org/documentation/)
- [Python Kafka客户端](https://kafka-python.readthedocs.io/)
- 项目现有代码：
  - [Common/Queue/KafkaManager.py](d:\desktop\Universidad\4_cursor\1\SD\practica\2\Common\Queue\KafkaManager.py)
  - [Driver/EV_Driver.py](d:\desktop\Universidad\4_cursor\1\SD\practica\2\Driver\EV_Driver.py)
  - [Core/Central/MessageDispatcher.py](d:\desktop\Universidad\4_cursor\1\SD\practica\2\Core\Central\MessageDispatcher.py)
