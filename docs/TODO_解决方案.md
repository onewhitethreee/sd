# TODO 项目解决方案

> 文档生成时间: 2025-11-03
> 代码库版本: startting_kafka 分支
> 分析范围: 全代码库 TODO/FIXME 注释

---

## 📋 目录

1. [总览](#总览)
2. [高优先级 TODOs](#高优先级-todos)
3. [中优先级 TODOs](#中优先级-todos)
4. [低优先级 TODOs](#低优先级-todos)
5. [实施计划](#实施计划)
6. [测试建议](#测试建议)

---

## 总览

### 统计信息

| 优先级 | 数量 | 预估工作量 | 风险等级 |
|--------|------|-----------|---------|
| 🔴 高优先级 | 3 | 4-7 小时 | 高 |
| 🟡 中优先级 | 2 | 2-3 小时 | 中 |
| 🟢 低优先级 | 1 | 2-3 小时 | 低 |
| **总计** | **6** | **8-13 小时** | - |

### TODO 分布

```
Charging_point/Monitor/EC_CP_M.py      ████████ 4 个
Core/Central/MessageDispatcher.py      ██ 1 个
Charging_point/Engine/EV_CP_E.py       ██ 1 个
MESSAGE_FLOW_DOCUMENTATION.md          ██ 1 个 (文档标记)
docs/项目架构分析与Kafka迁移指南.md    ██ 1 个 (架构问题)
```

---

## 🔴 高优先级 TODOs

### TODO-1: 认证功能未实现

#### 📍 位置
- **文件**: [MESSAGE_FLOW_DOCUMENTATION.md:187](../MESSAGE_FLOW_DOCUMENTATION.md#L187)
- **相关代码**: [EC_CP_M.py:288-303](../Charging_point/Monitor/EC_CP_M.py#L288-L303)
- **标记**: `❓ **未实现** | **TODO**`

#### 🔍 问题描述
Monitor → Central 的 `auth_request` 消息类型在文档中标记为"未实现"。虽然 Monitor 中已经有 `authenticate_charging_point()` 方法，但该方法从未被调用（注释写着 "TODO 这里没有调用"）。

**当前状态**:
```python
# EC_CP_M.py:288
# TODO 这里没有调用
def authenticate_charging_point(self):
    """
    认证充电点，现在通过 ConnectionManager.send() 发送。
    """
    self.logger.info(f"Authenticating charging point {self.args.id_cp}")
    if not self.central_conn_mgr.is_connected:
        self.logger.error("Cannot authenticate: not connected to Central.")
        return False
    auth_message = {
        "type": "auth_request",
        "message_id": str(uuid.uuid4()),
        "id": self.args.id_cp,
        "timestamp": int(time.time()),
    }
    return self.central_conn_mgr.send(auth_message)
```

#### ⚠️ 风险
- **安全风险**: 未经认证的充电桩可以直接注册到系统
- **业务风险**: 无法区分合法和非法充电桩
- **合规风险**: 缺少审计跟踪

#### 💡 解决方案

**步骤 1: 在 Central 添加认证处理器**

```python
# 文件: Core/Central/MessageDispatcher.py
# 在 MESSAGE_HANDLERS 字典中添加

self.MESSAGE_HANDLERS = {
    # ... 现有处理器 ...
    "auth_request": self._handle_auth_request,
}

def _handle_auth_request(self, client_id, message):
    """
    处理充电桩认证请求

    认证逻辑:
    1. 验证 cp_id 格式是否正确
    2. 检查 cp_id 是否在白名单中（可选）
    3. 验证是否已注册
    4. 记录认证日志
    """
    cp_id = message.get("cp_id") or message.get("id")
    message_id = message.get("message_id")

    if not cp_id:
        self.logger.error(f"Auth request missing cp_id: {message}")
        return self._create_failure_response(
            "auth_request", message_id, "缺少 cp_id 字段"
        )

    try:
        # 1. 验证格式（例如: CP001, CP002...）
        if not self._validate_cp_id_format(cp_id):
            self.logger.warning(f"Invalid CP ID format: {cp_id}")
            return self._create_failure_response(
                "auth_request", message_id, f"无效的 CP ID 格式: {cp_id}"
            )

        # 2. 检查是否已注册（认证前需要先注册）
        cp_info = self.charging_point_manager.get_charging_point_info(cp_id)
        if not cp_info:
            self.logger.warning(f"CP {cp_id} not registered, cannot authenticate")
            return self._create_failure_response(
                "auth_request", message_id, f"充电桩 {cp_id} 未注册，请先注册"
            )

        # 3. 执行认证（这里可以添加更复杂的认证逻辑，如密钥验证）
        # TODO: 未来可以添加基于证书或密钥的认证
        auth_success = True

        if auth_success:
            # 4. 更新认证状态
            self.charging_point_manager.update_auth_status(cp_id, authenticated=True)

            self.logger.info(f"✅ CP {cp_id} authenticated successfully")

            return self._create_success_response(
                "auth_request",
                message_id,
                f"充电桩 {cp_id} 认证成功"
            )
        else:
            self.logger.error(f"❌ CP {cp_id} authentication failed")
            return self._create_failure_response(
                "auth_request", message_id, "认证失败"
            )

    except Exception as e:
        self.logger.error(f"Error handling auth request: {e}", exc_info=True)
        return self._create_failure_response(
            "auth_request", message_id, f"认证处理失败: {e}"
        )

def _validate_cp_id_format(self, cp_id):
    """验证 CP ID 格式"""
    import re
    # 格式: CP + 3位数字，例如 CP001, CP002
    pattern = r'^CP\d{3}$'
    return bool(re.match(pattern, cp_id))
```

**步骤 2: 在 ChargingPointManager 添加认证状态管理**

```python
# 文件: Core/Central/ChargingPointManager.py

def update_auth_status(self, cp_id, authenticated):
    """
    更新充电桩认证状态

    Args:
        cp_id: 充电桩ID
        authenticated: 是否已认证
    """
    try:
        with self.lock:
            db_conn = self.charging_point_db.get_connection()
            cursor = db_conn.cursor()

            # 更新认证状态和认证时间
            cursor.execute(
                """
                UPDATE charging_points
                SET authenticated = ?, authenticated_at = ?
                WHERE id = ?
                """,
                (1 if authenticated else 0, int(time.time()) if authenticated else None, cp_id)
            )

            db_conn.commit()

            if cursor.rowcount > 0:
                self.logger.info(f"Updated auth status for CP {cp_id}: {authenticated}")
                return True
            else:
                self.logger.warning(f"CP {cp_id} not found for auth status update")
                return False

    except Exception as e:
        self.logger.error(f"Failed to update auth status for {cp_id}: {e}")
        return False

# 注意: 需要在数据库表中添加这两个字段
# ALTER TABLE charging_points ADD COLUMN authenticated INTEGER DEFAULT 0;
# ALTER TABLE charging_points ADD COLUMN authenticated_at INTEGER;
```

**步骤 3: 在 Monitor 的启动流程中调用认证**

```python
# 文件: Charging_point/Monitor/EC_CP_M.py

def _register_to_central(self):
    """
    向 Central 注册充电点
    修改：注册成功后立即进行认证
    """
    # ... 现有注册逻辑 ...

    # 发送注册请求
    if self.central_conn_mgr.send(register_message):
        self.logger.info("Registration request sent to Central.")

        # 等待注册响应（通过 _on_register_confirmed 处理）
        # 注册成功后会调用认证
        return True
    else:
        self.logger.error("Failed to send registration to Central.")
        return False

def _on_register_confirmed(self):
    """
    当收到注册确认响应时调用
    修改：注册确认后立即进行认证
    """
    self._registration_confirmed = True
    self.logger.info("✅ Registration confirmed by Central")

    # 🆕 注册成功后立即进行认证
    self._authenticate_after_registration()

    # 尝试切换到 ACTIVE 状态
    self._attempt_transition_to_active()

def _authenticate_after_registration(self):
    """注册成功后执行认证"""
    self.logger.info("Starting authentication after successful registration...")

    if self.authenticate_charging_point():
        self.logger.info("✅ Authentication request sent successfully")
    else:
        self.logger.error("❌ Failed to send authentication request")
        # 认证失败不影响注册状态，但会记录警告
        # 未来可以添加重试机制

# authenticate_charging_point() 方法保持不变，移除 TODO 注释
def authenticate_charging_point(self):
    """
    认证充电点，现在通过 ConnectionManager.send() 发送。
    注册成功后自动调用。
    """
    self.logger.info(f"Authenticating charging point {self.args.id_cp}")
    if not self.central_conn_mgr.is_connected:
        self.logger.error("Cannot authenticate: not connected to Central.")
        return False
    auth_message = {
        "type": "auth_request",
        "message_id": str(uuid.uuid4()),
        "id": self.args.id_cp,
        "timestamp": int(time.time()),
    }
    return self.central_conn_mgr.send(auth_message)
```

**步骤 4: 添加认证响应处理**

```python
# 文件: Charging_point/Monitor/MonitorMessageDispatcher.py

def dispatch_message(self, message):
    """分发消息到对应的处理器"""
    handlers = {
        # ... 现有处理器 ...
        "auth_response": self._handle_auth_response,
    }

    # ... 现有分发逻辑 ...

def _handle_auth_response(self, message):
    """处理认证响应"""
    success = message.get("success", False)
    message_content = message.get("message", "")

    if success:
        self.logger.info(f"✅ Authentication successful: {message_content}")
        # 可以设置认证状态标志
        self.monitor._authenticated = True
    else:
        self.logger.error(f"❌ Authentication failed: {message_content}")
        self.monitor._authenticated = False
        # 可以触发重试或报警
```

#### ✅ 验收标准
1. Monitor 启动后能自动发送认证请求
2. Central 能正确处理认证请求并返回响应
3. 认证失败时有明确的错误信息
4. 数据库中记录认证状态和时间
5. 日志中能看到完整的认证流程

#### ⏱️ 预估时间
- 开发: 2-3 小时
- 测试: 1 小时
- **总计: 3-4 小时**

---

### TODO-2: 健康检查线程停止机制不完善

#### 📍 位置
- **文件**: [EC_CP_M.py:216](../Charging_point/Monitor/EC_CP_M.py#L216)
- **标记**: `# TODO 这里也没有停止啊？`

#### 🔍 问题描述
`_stop_engine_health_check_thread()` 和 `_stop_heartbeat_thread()` 方法没有显式的停止机制，只是依赖线程自己检查 `self.running` 标志。这可能导致：
1. 线程无法及时停止
2. 资源泄漏
3. 程序退出时线程仍在运行

**当前实现**:
```python
# EC_CP_M.py:217
def _stop_engine_health_check_thread(self):
    """停止对 Engine 的健康检查线程"""
    if self._engine_health_thread and self._engine_health_thread.is_alive():
        self.logger.info("Stopping Engine health check thread.")
        # 通过设置 running 标志让线程自然退出
        # 这里假设线程会检查 self.running 和 conn_mgr.is_connected
        # 因为我们没有单独的停止事件，所以只能依赖这些条件
        # 实际上，线程会在下一次循环时检测到条件变化并退出
    else:
        self.logger.debug("Engine health check thread is not running.")
```

#### ⚠️ 风险
- **资源泄漏**: 线程可能无法正确清理
- **退出延迟**: 程序退出时可能需要等待 sleep 结束
- **僵尸线程**: 在异常情况下可能产生僵尸线程

#### 💡 解决方案

**实现显式的线程停止事件**

```python
# 文件: Charging_point/Monitor/EC_CP_M.py

class Monitor:
    def __init__(self, args):
        # ... 现有初始化 ...

        # 🆕 添加线程停止事件
        self._stop_health_check_event = threading.Event()
        self._stop_heartbeat_event = threading.Event()

        # 设置合理的超时时间
        self.THREAD_JOIN_TIMEOUT = 5  # 秒

    def _stop_engine_health_check_thread(self):
        """停止对 Engine 的健康检查线程（改进版）"""
        if self._engine_health_thread and self._engine_health_thread.is_alive():
            self.logger.info("Stopping Engine health check thread...")

            # 1. 设置停止事件
            self._stop_health_check_event.set()

            # 2. 等待线程结束（带超时）
            self._engine_health_thread.join(timeout=self.THREAD_JOIN_TIMEOUT)

            # 3. 检查线程是否成功停止
            if self._engine_health_thread.is_alive():
                self.logger.warning(
                    "Engine health check thread did not stop gracefully within timeout"
                )
            else:
                self.logger.info("✅ Engine health check thread stopped successfully")
        else:
            self.logger.debug("Engine health check thread is not running.")

    def _stop_heartbeat_thread(self):
        """停止发送心跳的线程（改进版）"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self.logger.info("Stopping heartbeat thread for Central...")

            # 1. 设置停止事件
            self._stop_heartbeat_event.set()

            # 2. 等待线程结束（带超时）
            self._heartbeat_thread.join(timeout=self.THREAD_JOIN_TIMEOUT)

            # 3. 检查线程是否成功停止
            if self._heartbeat_thread.is_alive():
                self.logger.warning(
                    "Heartbeat thread did not stop gracefully within timeout"
                )
            else:
                self.logger.info("✅ Heartbeat thread stopped successfully")
        else:
            self.logger.debug("Heartbeat thread for Central is not running.")

    def _check_engine_health(self):
        """
        定期检查 Engine 的健康状态（改进版）
        使用 Event.wait() 替代 time.sleep() 以支持立即停止
        """
        self.logger.info("Engine health check thread started.")

        while not self._stop_health_check_event.is_set():
            # 检查是否应该继续运行
            if not self.running or not self.engine_conn_mgr:
                break

            if self.engine_conn_mgr.is_connected:
                # 发送健康检查
                health_check_msg = {
                    "type": "health_check_request",
                    "message_id": str(uuid.uuid4()),
                    "timestamp": int(time.time()),
                }

                if self.engine_conn_mgr.send(health_check_msg):
                    self.logger.debug("Health check sent to Engine.")
                else:
                    self.logger.warning("Failed to send health check to Engine.")

            # 使用 Event.wait() 替代 time.sleep()
            # 这样可以在收到停止信号时立即退出，而不用等待 sleep 结束
            self._stop_health_check_event.wait(timeout=self.HEALTH_CHECK_INTERVAL)

        self.logger.info("Engine health check thread stopped.")

    def _send_heartbeat(self):
        """
        发送心跳消息以保持与central的连接（改进版）
        使用 Event.wait() 替代 time.sleep() 以支持立即停止
        """
        self.logger.info("Heartbeat thread started.")

        while not self._stop_heartbeat_event.is_set():
            # 检查是否应该继续运行
            if not self.running or not self.central_conn_mgr:
                break

            if self.central_conn_mgr.is_connected:
                heartbeat_msg = {
                    "type": "heartbeat_request",
                    "message_id": str(uuid.uuid4()),
                    "id": self.args.id_cp,
                }

                if self.central_conn_mgr.send(heartbeat_msg):
                    self.logger.debug("Heartbeat sent to Central.")
                else:
                    self.logger.error(
                        "Failed to send heartbeat to Central (might be disconnected internally)."
                    )

            # 使用 Event.wait() 替代 time.sleep()
            self._stop_heartbeat_event.wait(timeout=self.HEARTBEAT_INTERVAL)

        self.logger.info("Heartbeat thread for Central has stopped.")

    def _start_engine_health_check_thread(self):
        """启动对 Engine 的健康检查线程（改进版）"""
        if self._engine_health_thread and self._engine_health_thread.is_alive():
            self.logger.debug("Engine health check thread already running.")
            return

        # 🆕 重置停止事件（允许重启线程）
        self._stop_health_check_event.clear()

        self.logger.info("Starting Engine health check thread.")
        self._engine_health_thread = threading.Thread(
            target=self._check_engine_health,
            daemon=True,
            name="EngineHealthCheckThread",
        )
        self._engine_health_thread.start()

    def _start_heartbeat_thread(self):
        """启动发送心跳的线程（改进版）"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self.logger.debug("Heartbeat thread for Central already running.")
            return

        # 🆕 重置停止事件（允许重启线程）
        self._stop_heartbeat_event.clear()

        self.logger.info("Starting heartbeat thread for Central.")
        self._heartbeat_thread = threading.Thread(
            target=self._send_heartbeat,
            daemon=True,
            name="CentralHeartbeatThread"
        )
        self._heartbeat_thread.start()

    def stop(self):
        """停止 Monitor（改进版，确保所有线程正确停止）"""
        self.logger.info("Stopping Monitor...")
        self.running = False

        # 🆕 停止所有后台线程
        self._stop_heartbeat_thread()
        self._stop_engine_health_check_thread()

        # 关闭连接
        if self.central_conn_mgr:
            self.central_conn_mgr.close()
        if self.engine_conn_mgr:
            self.engine_conn_mgr.close()

        self.logger.info("✅ Monitor stopped successfully")
```

#### ✅ 验收标准
1. 调用 `stop()` 时所有线程能在 5 秒内停止
2. 不再有僵尸线程
3. 使用 Ctrl+C 退出时程序能立即响应
4. 线程停止后日志中有明确的确认信息
5. 线程可以被重新启动（Event 被正确重置）

#### ⏱️ 预估时间
- 开发: 1 小时
- 测试: 1 小时
- **总计: 2 小时**

---

### TODO-3: 使用常量替代硬编码字符串

#### 📍 位置
- **文件 1**: [EC_CP_M.py:522](../Charging_point/Monitor/EC_CP_M.py#L522) - "TODO 这里用常量"
- **文件 2**: [EC_CP_M.py:559](../Charging_point/Monitor/EC_CP_M.py#L559) - "TODO 这里用response常量"

#### 🔍 问题描述
代码中多处使用硬编码的字符串来表示消息类型，例如：
```python
charging_data_message = {
    "type": "charging_data",  # 硬编码字符串
    # ...
}

completion_message = {
    "type": "charge_completion",  # 硬编码字符串
    # ...
}
```

#### ⚠️ 风险
- **拼写错误**: 容易打错字，导致消息无法识别
- **维护困难**: 修改消息类型时需要全局搜索替换
- **代码可读性差**: 字符串字面量没有 IDE 自动补全
- **重构风险**: 重命名时容易遗漏

#### 💡 解决方案

**步骤 1: 创建消息类型常量文件**

```python
# 文件: Common/Constants/MessageTypes.py

"""
消息类型常量定义

用于统一管理系统中所有消息类型，避免硬编码字符串。
"""


class MessageTypes:
    """消息类型常量类"""

    # ========== Monitor → Central 消息 ==========
    REGISTER_REQUEST = "register_request"
    REGISTER_RESPONSE = "register_response"

    HEARTBEAT_REQUEST = "heartbeat_request"
    HEARTBEAT_RESPONSE = "heartbeat_response"

    AUTH_REQUEST = "auth_request"
    AUTH_RESPONSE = "auth_response"

    FAULT_NOTIFICATION = "fault_notification"
    STATUS_UPDATE = "status_update"

    CHARGING_DATA = "charging_data"
    CHARGE_COMPLETION = "charge_completion"

    # ========== Central → Monitor 消息 ==========
    START_CHARGING_COMMAND = "start_charging_command"
    STOP_CHARGING_COMMAND = "stop_charging_command"

    # ========== Monitor ↔ Engine 消息 ==========
    HEALTH_CHECK_REQUEST = "health_check_request"
    HEALTH_CHECK_RESPONSE = "health_check_response"

    ENGINE_START_CHARGING = "start_charging"
    ENGINE_STOP_CHARGING = "stop_charging"
    ENGINE_CHARGING_STATUS = "charging_status"

    # ========== Driver → Central 消息 (Kafka) ==========
    CHARGE_REQUEST = "charge_request"
    CHARGE_REQUEST_RESPONSE = "charge_request_response"

    STOP_CHARGING_REQUEST = "stop_charging_request"
    STOP_CHARGING_RESPONSE = "stop_charging_response"

    AVAILABLE_CPS_REQUEST = "available_cps_request"
    AVAILABLE_CPS_RESPONSE = "available_cps_response"

    CHARGING_HISTORY_REQUEST = "charging_history_request"
    CHARGING_HISTORY_RESPONSE = "charging_history_response"

    CHARGING_STATUS_UPDATE = "charging_status_update"

    # ========== 维护通知 ==========
    MAINTENANCE_ALERT = "maintenance_alert"

    @classmethod
    def all_types(cls):
        """返回所有消息类型的列表"""
        return [
            value for name, value in vars(cls).items()
            if not name.startswith('_') and isinstance(value, str)
        ]

    @classmethod
    def is_valid(cls, msg_type):
        """检查消息类型是否有效"""
        return msg_type in cls.all_types()


# 为了向后兼容，也可以提供函数式访问
def get_message_type(type_name):
    """
    获取消息类型常量

    Args:
        type_name: 消息类型名称（例如 "REGISTER_REQUEST"）

    Returns:
        消息类型字符串，如果不存在则返回 None
    """
    return getattr(MessageTypes, type_name, None)
```

**步骤 2: 创建消息字段常量**

```python
# 文件: Common/Constants/MessageFields.py

"""
消息字段常量定义

定义消息中常用的字段名，避免硬编码。
"""


class MessageFields:
    """消息字段常量类"""

    # 通用字段
    TYPE = "type"
    MESSAGE_ID = "message_id"
    TIMESTAMP = "timestamp"
    SUCCESS = "success"
    MESSAGE = "message"

    # 身份字段
    CP_ID = "cp_id"
    DRIVER_ID = "driver_id"
    SESSION_ID = "session_id"

    # 充电相关
    ENERGY_CONSUMED_KWH = "energy_consumed_kwh"
    TOTAL_COST = "total_cost"
    CHARGING_RATE = "charging_rate"
    MAX_CHARGING_RATE_KW = "max_charging_rate_kw"

    # 状态相关
    STATUS = "status"
    FAULT_TYPE = "fault_type"
    FAILURE_INFO = "failure_info"

    # 位置和价格
    LOCATION = "location"
    PRICE_PER_KWH = "price_per_kwh"

    # 查询相关
    LIMIT = "limit"
    OFFSET = "offset"
```

**步骤 3: 创建统一导入文件**

```python
# 文件: Common/Constants/__init__.py

"""
常量模块

集中管理系统中的所有常量定义。
"""

from .MessageTypes import MessageTypes, get_message_type
from .MessageFields import MessageFields

__all__ = [
    'MessageTypes',
    'MessageFields',
    'get_message_type',
]
```

**步骤 4: 替换 EC_CP_M.py 中的硬编码**

```python
# 文件: Charging_point/Monitor/EC_CP_M.py

# 在文件顶部添加导入
from Common.Constants import MessageTypes, MessageFields

class Monitor:
    # ... 其他代码 ...

    def _handle_charging_data_from_engine(self, message):
        """处理来自Engine的充电数据（转发）- 使用常量版本"""
        self.logger.info("Received charging data from Engine, forwarding to Central.")

        if not self.central_conn_mgr.is_connected:
            self.logger.warning(
                "Not connected to Central, cannot forward charging data."
            )
            return False

        # 验证必需字段
        required_fields = [
            MessageFields.SESSION_ID,
            MessageFields.ENERGY_CONSUMED_KWH,
            MessageFields.TOTAL_COST
        ]
        missing_fields = [
            field for field in required_fields if message.get(field) is None
        ]
        if missing_fields:
            self.logger.error(
                f"Charging data from Engine missing required fields: {', '.join(missing_fields)}"
            )
            return False

        # ✅ 使用常量替代硬编码字符串
        charging_data_message = {
            MessageFields.TYPE: MessageTypes.CHARGING_DATA,
            MessageFields.MESSAGE_ID: str(uuid.uuid4()),
            MessageFields.CP_ID: self.args.id_cp,
            MessageFields.SESSION_ID: message.get(MessageFields.SESSION_ID),
            MessageFields.ENERGY_CONSUMED_KWH: message.get(MessageFields.ENERGY_CONSUMED_KWH),
            MessageFields.TOTAL_COST: message.get(MessageFields.TOTAL_COST),
        }

        if self.central_conn_mgr.send(charging_data_message):
            self.logger.debug("Charging data forwarded to Central.")
            return True
        else:
            self.logger.error("Failed to forward charging data to Central.")
            return False

    def _handle_charging_completion_from_engine(self, message):
        """处理来自Engine的充电完成通知（转发）- 使用常量版本"""
        self.logger.info("Received charging completion from Engine.")

        if not self.central_conn_mgr.is_connected:
            self.logger.warning(
                "Not connected to Central, cannot forward charging completion."
            )
            return False

        # 验证必需字段
        required_fields = [
            MessageFields.SESSION_ID,
            MessageFields.ENERGY_CONSUMED_KWH,
            MessageFields.TOTAL_COST
        ]
        missing_fields = [
            field for field in required_fields if message.get(field) is None
        ]
        if missing_fields:
            self.logger.error(
                f"Charging completion from Engine missing required fields: {', '.join(missing_fields)}"
            )
            return False

        # ✅ 使用常量替代硬编码字符串
        completion_message = {
            MessageFields.TYPE: MessageTypes.CHARGE_COMPLETION,
            MessageFields.MESSAGE_ID: message.get(MessageFields.MESSAGE_ID),
            MessageFields.CP_ID: message.get(MessageFields.CP_ID),
            MessageFields.SESSION_ID: message.get(MessageFields.SESSION_ID),
            MessageFields.ENERGY_CONSUMED_KWH: message.get(MessageFields.ENERGY_CONSUMED_KWH),
            MessageFields.TOTAL_COST: message.get(MessageFields.TOTAL_COST),
        }

        if self.central_conn_mgr.send(completion_message):
            self.logger.info("Charging completion forwarded to Central.")
            return True
        else:
            self.logger.error("Failed to forward charging completion to Central.")
            return False
```

**步骤 5: 批量替换其他文件**

使用以下脚本辅助批量替换（需要人工审查）：

```python
# 工具脚本: scripts/replace_message_types.py

"""
辅助脚本：批量替换消息类型硬编码字符串为常量

使用方法:
1. 先备份代码
2. 运行脚本生成替换建议
3. 人工审查并应用替换
"""

import re
import os

# 消息类型映射
MESSAGE_TYPE_MAP = {
    '"type": "register_request"': 'MessageFields.TYPE: MessageTypes.REGISTER_REQUEST',
    '"type": "heartbeat_request"': 'MessageFields.TYPE: MessageTypes.HEARTBEAT_REQUEST',
    '"type": "auth_request"': 'MessageFields.TYPE: MessageTypes.AUTH_REQUEST',
    '"type": "charging_data"': 'MessageFields.TYPE: MessageTypes.CHARGING_DATA',
    '"type": "charge_completion"': 'MessageFields.TYPE: MessageTypes.CHARGE_COMPLETION',
    # ... 添加更多映射
}

def scan_and_suggest_replacements(directory):
    """扫描目录并建议替换"""
    for root, dirs, files in os.walk(directory):
        # 跳过 .git 等目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                suggest_replacements_for_file(filepath)

def suggest_replacements_for_file(filepath):
    """为单个文件建议替换"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    suggestions = []
    for old_pattern, new_pattern in MESSAGE_TYPE_MAP.items():
        if old_pattern in content:
            suggestions.append((old_pattern, new_pattern))

    if suggestions:
        print(f"\n文件: {filepath}")
        for old, new in suggestions:
            print(f"  {old} -> {new}")

if __name__ == "__main__":
    scan_and_suggest_replacements(".")
```

#### ✅ 验收标准
1. 所有消息类型都使用 `MessageTypes` 常量
2. 所有字段名都使用 `MessageFields` 常量
3. IDE 能提供自动补全
4. 现有测试全部通过
5. 没有引入新的 bug

#### ⏱️ 预估时间
- 创建常量文件: 30 分钟
- 替换代码: 1-2 小时
- 测试验证: 30 分钟
- **总计: 2-3 小时**

---

## 🟡 中优先级 TODOs

### TODO-4: 维护人员通知逻辑

#### 📍 位置
- **文件**: [MessageDispatcher.py:681](../Core/Central/MessageDispatcher.py#L681)
- **标记**: `# TODO: 在这里可以添加通知维护人员的逻辑`

#### 🔍 问题描述
当充电桩发生故障时，系统会更新数据库状态并记录日志，但没有实际通知维护人员的机制。故障可能无法及时被发现和处理。

**当前代码**:
```python
def _handle_fault_notification(self, client_id, message):
    # ... 更新数据库 ...
    self.logger.error(f"充电点 {cp_id} 故障: {failure_info}")

    # TODO: 在这里可以添加通知维护人员的逻辑

    return self._create_success_response(...)
```

#### ⚠️ 风险
- **运维盲区**: 故障无法及时发现
- **用户体验差**: 故障充电桩长时间不修复
- **收入损失**: 故障时间过长导致业务损失

#### 💡 解决方案

**方案 1: 通过 Kafka 发送维护通知（推荐）**

```python
# 文件: Core/Central/MessageDispatcher.py

from Common.Constants import MessageTypes, MessageFields

class MessageDispatcher:
    def __init__(self, ...):
        # ... 现有初始化 ...

        # 创建维护通知专用主题
        if self.kafka_manager:
            self.kafka_manager.create_topic_if_not_exists(
                "maintenance_notifications",
                num_partitions=1,
                replication_factor=1
            )

    def _handle_fault_notification(self, client_id, message):
        """处理故障通知（添加维护人员通知）"""
        cp_id = message.get(MessageFields.CP_ID) or message.get("id")
        fault_type = message.get(MessageFields.FAULT_TYPE, "UNKNOWN")
        failure_info = message.get(MessageFields.FAILURE_INFO, "No details provided")
        message_id = message.get(MessageFields.MESSAGE_ID)

        if not cp_id:
            self.logger.error(f"Fault notification missing CP ID: {message}")
            return self._create_failure_response(
                "fault_notification", message_id, "缺少充电点 ID"
            )

        try:
            # 1. 更新数据库状态
            self.charging_point_manager.update_charging_point_status(
                cp_id=cp_id, status=Status.FAULTY.value
            )

            self.logger.error(f"充电点 {cp_id} 故障: {failure_info}")

            # 2. ✅ 发送维护通知
            self._notify_maintenance_team(cp_id, fault_type, failure_info)

            return self._create_success_response(
                "fault_notification",
                message_id,
                f"故障通知已记录，充电点 {cp_id} 状态已更新为故障",
            )
        except Exception as e:
            self.logger.error(f"处理故障通知失败: {e}")
            return self._create_failure_response(
                "fault_notification", message_id, f"故障通知处理失败: {e}"
            )

    def _notify_maintenance_team(self, cp_id, fault_type, failure_info):
        """
        通知维护团队

        使用 Kafka 发送维护通知，维护系统可以订阅该主题
        """
        try:
            # 获取充电点详细信息
            cp_info = self.charging_point_manager.get_charging_point_info(cp_id)

            # 计算故障严重程度
            severity = self._calculate_fault_severity(fault_type)

            notification = {
                MessageFields.TYPE: MessageTypes.MAINTENANCE_ALERT,
                MessageFields.MESSAGE_ID: str(uuid.uuid4()),
                MessageFields.CP_ID: cp_id,
                MessageFields.FAULT_TYPE: fault_type,
                MessageFields.FAILURE_INFO: failure_info,
                MessageFields.TIMESTAMP: int(time.time()),
                "severity": severity,  # HIGH, MEDIUM, LOW
                "location": cp_info.get("location") if cp_info else "Unknown",
                "requires_immediate_action": severity == "HIGH",
            }

            # 发送到 Kafka 维护通知主题
            if self.kafka_manager and self.kafka_manager.is_connected():
                success = self.kafka_manager.produce_message(
                    "maintenance_notifications",
                    notification
                )

                if success:
                    self.logger.info(
                        f"✅ Maintenance notification sent for CP {cp_id} "
                        f"(severity: {severity})"
                    )
                else:
                    self.logger.error(
                        f"❌ Failed to send maintenance notification for CP {cp_id}"
                    )
            else:
                self.logger.warning(
                    "Kafka not available, maintenance notification not sent"
                )
                # 降级方案：写入专用日志文件
                self._log_maintenance_alert_to_file(notification)

        except Exception as e:
            self.logger.error(f"Error sending maintenance notification: {e}", exc_info=True)

    def _calculate_fault_severity(self, fault_type):
        """
        根据故障类型计算严重程度

        Returns:
            "HIGH", "MEDIUM", 或 "LOW"
        """
        high_severity_faults = [
            "ENGINE_FAILURE",
            "COMMUNICATION_LOST",
            "SAFETY_CRITICAL",
            "FIRE_HAZARD",
        ]

        medium_severity_faults = [
            "CHARGING_ERROR",
            "SENSOR_MALFUNCTION",
            "CONNECTION_TIMEOUT",
        ]

        if fault_type in high_severity_faults:
            return "HIGH"
        elif fault_type in medium_severity_faults:
            return "MEDIUM"
        else:
            return "LOW"

    def _log_maintenance_alert_to_file(self, notification):
        """
        降级方案：当 Kafka 不可用时，写入专用日志文件
        外部监控系统可以监控此文件
        """
        import json

        log_file = "logs/maintenance_alerts.log"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(notification) + "\n")

        self.logger.info(f"Maintenance alert logged to file: {log_file}")
```

**方案 2: 创建独立的维护通知服务（可选）**

```python
# 文件: Core/Maintenance/MaintenanceNotifier.py

"""
维护通知服务

订阅 maintenance_notifications 主题，并通过多种渠道发送通知：
- 邮件
- 短信
- Slack/钉钉/企业微信
- 推送通知
"""

import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from Common.Queue.KafkaManager import KafkaManager
from Common.Config.ConfigManager import ConfigManager
from Common.Config.CustomLogger import CustomLogger


class MaintenanceNotifier:
    """维护通知服务"""

    def __init__(self):
        self.logger = CustomLogger.get_logger()
        self.config = ConfigManager()

        # 从配置文件读取通知设置
        self.email_enabled = self.config.get("MAINTENANCE_EMAIL_ENABLED", False)
        self.email_recipients = self.config.get("MAINTENANCE_EMAIL_RECIPIENTS", [])
        self.smtp_config = self.config.get("SMTP_CONFIG", {})

        # 初始化 Kafka
        broker_address = self.config.get_broker()
        self.kafka_manager = KafkaManager(broker_address, self.logger)

        self.running = False

    def start(self):
        """启动维护通知服务"""
        self.logger.info("Starting Maintenance Notifier service...")

        # 初始化 Kafka 消费者
        if self.kafka_manager.init_producer():
            self.kafka_manager.start()

            self.kafka_manager.init_consumer(
                "maintenance_notifications",
                "maintenance_notifier_group",
                self._handle_maintenance_alert
            )

            self.running = True
            self.logger.info("✅ Maintenance Notifier service started")

            # 保持运行
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.logger.info("Shutting down...")
        else:
            self.logger.error("Failed to start Maintenance Notifier")

    def stop(self):
        """停止服务"""
        self.running = False
        if self.kafka_manager:
            self.kafka_manager.stop()

    def _handle_maintenance_alert(self, alert):
        """处理维护警报"""
        try:
            cp_id = alert.get("cp_id")
            severity = alert.get("severity")
            fault_type = alert.get("fault_type")
            failure_info = alert.get("failure_info")
            location = alert.get("location")

            self.logger.warning(
                f"🚨 Maintenance Alert: CP {cp_id} at {location} "
                f"has fault ({fault_type}) - Severity: {severity}"
            )

            # 发送邮件通知
            if self.email_enabled:
                self._send_email_notification(alert)

            # 可以添加更多通知渠道
            # self._send_sms_notification(alert)
            # self._send_slack_notification(alert)

        except Exception as e:
            self.logger.error(f"Error handling maintenance alert: {e}", exc_info=True)

    def _send_email_notification(self, alert):
        """发送邮件通知"""
        try:
            cp_id = alert.get("cp_id")
            severity = alert.get("severity")
            fault_type = alert.get("fault_type")
            failure_info = alert.get("failure_info")
            location = alert.get("location")
            timestamp = alert.get("timestamp")

            # 构建邮件内容
            subject = f"[{severity}] Charging Point Fault - {cp_id}"

            body = f"""
Charging Point Fault Notification

Severity: {severity}
Charging Point ID: {cp_id}
Location: {location}
Fault Type: {fault_type}
Details: {failure_info}
Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}

Please investigate and resolve this issue as soon as possible.

---
This is an automated message from the EV Charging Management System.
            """

            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = self.smtp_config.get('sender')
            msg['To'] = ', '.join(self.email_recipients)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            # 发送邮件
            with smtplib.SMTP(
                self.smtp_config.get('host'),
                self.smtp_config.get('port')
            ) as server:
                server.starttls()
                server.login(
                    self.smtp_config.get('username'),
                    self.smtp_config.get('password')
                )
                server.send_message(msg)

            self.logger.info(f"✅ Email notification sent for CP {cp_id}")

        except Exception as e:
            self.logger.error(f"Failed to send email notification: {e}")


if __name__ == "__main__":
    notifier = MaintenanceNotifier()
    notifier.start()
```

**配置文件示例**:

```env
# .env 添加维护通知配置

# 维护通知配置
MAINTENANCE_EMAIL_ENABLED=true
MAINTENANCE_EMAIL_RECIPIENTS=maintenance@example.com,admin@example.com

# SMTP 配置
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_SENDER=ev-system@example.com
```

#### ✅ 验收标准
1. 故障发生时能自动发送 Kafka 消息
2. 维护通知服务能接收并处理通知
3. 邮件发送成功（如果启用）
4. 通知中包含所有必要信息
5. 严重故障能被正确识别并优先处理

#### ⏱️ 预估时间
- 方案1（Kafka通知）: 1 小时
- 方案2（独立服务）: 2-3 小时
- **总计: 1-3 小时**

---

### TODO-5: Engine Monitor 断连超时处理

#### 📍 位置
- **文件**: [EV_CP_E.py:125](../Charging_point/Engine/EV_CP_E.py#L125)
- **标记**: `# TODO 如果长时间没有 monitor 连接，可以考虑定时检查并切换状态。`

#### 🔍 问题描述
当 Monitor 断开连接时，Engine 会停止充电但不会立即进入 FAULTY 状态。如果 Monitor 长时间不重连，Engine 应该转换到 FAULTY 状态并通知 Central。

**当前代码**:
```python
def _handle_monitor_disconnect(self):
    """处理Monitor断开连接"""
    if self.is_charging:
        self.logger.warning(
            "Monitor disconnected during charging - stopping charging for safety"
        )
        self._stop_charging_session()

    # 不要立即进入 FAULTY 状态，Monitor 可能会重连。
    # TODO 如果长时间没有 monitor 连接，可以考虑定时检查并切换状态。
```

#### ⚠️ 风险
- **状态不一致**: Engine 实际有问题但状态显示正常
- **资源浪费**: 用户尝试使用实际不可用的充电桩
- **监控盲区**: 运维人员不知道 Engine 已脱离管理

#### 💡 解决方案

```python
# 文件: Charging_point/Engine/EV_CP_E.py

class Engine:
    # 配置常量
    MONITOR_DISCONNECT_TIMEOUT = 300  # 5分钟无连接后进入 FAULTY
    MONITOR_RECONNECT_CHECK_INTERVAL = 30  # 每30秒检查一次

    def __init__(self, ...):
        # ... 现有初始化 ...

        # 🆕 监控断连相关
        self.monitor_disconnect_time = None
        self._monitor_timeout_thread = None
        self._stop_monitor_timeout_check = threading.Event()

    def _handle_monitor_disconnect(self):
        """处理Monitor断开连接（改进版）"""
        self.logger.warning("Monitor disconnected")

        # 1. 如果正在充电，立即停止（安全优先）
        if self.is_charging:
            self.logger.warning(
                "Monitor disconnected during charging - stopping charging for safety"
            )
            self._stop_charging_session()

        # 2. 记录断连时间
        self.monitor_disconnect_time = time.time()

        # 3. 启动超时检查线程
        self._start_monitor_timeout_check()

    def _start_monitor_timeout_check(self):
        """启动 Monitor 断连超时检查线程"""
        if self._monitor_timeout_thread and self._monitor_timeout_thread.is_alive():
            self.logger.debug("Monitor timeout check thread already running")
            return

        self._stop_monitor_timeout_check.clear()

        self.logger.info(
            f"Starting monitor timeout check "
            f"(will enter FAULTY after {self.MONITOR_DISCONNECT_TIMEOUT}s)"
        )

        self._monitor_timeout_thread = threading.Thread(
            target=self._monitor_disconnect_timeout_handler,
            daemon=True,
            name="MonitorTimeoutCheckThread"
        )
        self._monitor_timeout_thread.start()

    def _stop_monitor_timeout_check(self):
        """停止超时检查线程"""
        if self._monitor_timeout_thread and self._monitor_timeout_thread.is_alive():
            self.logger.info("Stopping monitor timeout check thread")
            self._stop_monitor_timeout_check.set()
            self._monitor_timeout_thread.join(timeout=5)

    def _monitor_disconnect_timeout_handler(self):
        """
        Monitor 断连超时处理线程

        每隔一段时间检查 Monitor 是否重连：
        - 如果重连，则取消超时检查
        - 如果超时仍未重连，则进入 FAULTY 状态
        """
        disconnect_start_time = self.monitor_disconnect_time

        while not self._stop_monitor_timeout_check.is_set():
            # 检查 Monitor 是否已重连
            if self.monitor_server and self.monitor_server.is_connected():
                self.logger.info(
                    "✅ Monitor reconnected, cancelling timeout check"
                )
                self.monitor_disconnect_time = None
                return

            # 计算断连时长
            if disconnect_start_time:
                elapsed_time = time.time() - disconnect_start_time
                remaining_time = self.MONITOR_DISCONNECT_TIMEOUT - elapsed_time

                if remaining_time <= 0:
                    # 超时，进入 FAULTY 状态
                    self.logger.error(
                        f"❌ Monitor disconnected for more than "
                        f"{self.MONITOR_DISCONNECT_TIMEOUT}s, entering FAULTY state"
                    )
                    self._transition_to_faulty_due_to_monitor_timeout()
                    return
                else:
                    # 定期记录剩余时间
                    if int(remaining_time) % 60 == 0:  # 每分钟记录一次
                        self.logger.warning(
                            f"Monitor still disconnected, "
                            f"entering FAULTY in {int(remaining_time)}s"
                        )

            # 等待下一次检查
            self._stop_monitor_timeout_check.wait(
                timeout=self.MONITOR_RECONNECT_CHECK_INTERVAL
            )

        self.logger.info("Monitor timeout check thread stopped")

    def _transition_to_faulty_due_to_monitor_timeout(self):
        """由于 Monitor 超时而转换到 FAULTY 状态"""
        try:
            # 1. 更新状态
            self.status = Status.FAULTY.value
            self.logger.error(f"Engine status changed to FAULTY (Monitor timeout)")

            # 2. 如果有 Monitor 连接（虽然不太可能），尝试通知
            if self.monitor_server:
                fault_notification = {
                    "type": "fault_notification",
                    "message_id": str(uuid.uuid4()),
                    "fault_type": "MONITOR_TIMEOUT",
                    "failure_info": (
                        f"Monitor disconnected for more than "
                        f"{self.MONITOR_DISCONNECT_TIMEOUT}s"
                    ),
                    "timestamp": int(time.time()),
                }

                # 尝试发送（可能失败）
                try:
                    self.monitor_server.send_to_client(fault_notification)
                    self.logger.info("Fault notification sent to Monitor")
                except Exception as e:
                    self.logger.debug(f"Cannot send to Monitor (expected): {e}")

            # 3. 停止所有活动
            self._stop_all_activities()

        except Exception as e:
            self.logger.error(
                f"Error transitioning to FAULTY state: {e}",
                exc_info=True
            )

    def _stop_all_activities(self):
        """停止所有活动（进入故障状态时调用）"""
        # 停止充电（如果还在充电）
        if self.is_charging:
            self._stop_charging_session()

        # 清理资源
        self.logger.info("All activities stopped due to FAULTY state")

    def _handle_monitor_reconnect(self):
        """
        处理 Monitor 重连（新增方法）

        当 Monitor 重新连接时调用此方法
        """
        self.logger.info("✅ Monitor reconnected")

        # 1. 清除断连时间
        self.monitor_disconnect_time = None

        # 2. 停止超时检查线程
        self._stop_monitor_timeout_check()

        # 3. 如果当前状态是 FAULTY 且是由于 Monitor 超时导致的，可以考虑恢复
        # （这需要根据业务规则决定，这里仅作示例）
        if self.status == Status.FAULTY.value:
            self.logger.info(
                "Engine is FAULTY, may require manual intervention to recover"
            )
            # 可以发送通知给 Monitor，询问是否应该恢复
        else:
            self.logger.info(f"Engine status: {self.status}, no action needed")

    # 在 Monitor 连接建立时调用 _handle_monitor_reconnect
    def _start_monitor_server(self):
        """启动服务器等待Monitor连接（修改版）"""
        try:
            self.monitor_server = MySocketServer(
                host=self.engine_listen_address[0],
                port=self.engine_listen_address[1],
                logger=self.logger,
                message_callback=self._process_monitor_message,
                disconnect_callback=self._handle_monitor_disconnect,
                connect_callback=self._handle_monitor_reconnect,  # 🆕 添加重连回调
            )

            self.monitor_server.start()
            # ... 其余代码
```

**同时需要修改 MySocketServer 支持连接回调**:

```python
# 文件: Common/Socket/MySocketServer.py

class MySocketServer:
    def __init__(
        self,
        host,
        port,
        logger,
        message_callback=None,
        disconnect_callback=None,
        connect_callback=None  # 🆕 新增参数
    ):
        # ... 现有代码 ...
        self.connect_callback = connect_callback

    def _handle_client(self, client_socket, address):
        """处理客户端连接（修改版）"""
        self.logger.info(f"New client connected: {address}")

        with self.lock:
            self.client_socket = client_socket
            self.client_address = address
            self.is_client_connected = True

        # 🆕 触发连接回调
        if self.connect_callback:
            try:
                self.connect_callback()
            except Exception as e:
                self.logger.error(f"Error in connect callback: {e}")

        # ... 其余处理逻辑
```

#### ✅ 验收标准
1. Monitor 断开后 5 分钟，Engine 自动进入 FAULTY 状态
2. Monitor 在超时前重连，不进入 FAULTY 状态
3. 超时检查线程能正确启动和停止
4. 日志中能看到倒计时警告
5. 进入 FAULTY 后能正确停止所有活动

#### ⏱️ 预估时间
- 开发: 1.5 小时
- 测试: 30 分钟
- **总计: 2 小时**

---

## 🟢 低优先级 TODOs

### TODO-6: 数据库事务支持

#### 📍 位置
- **文档**: [docs/项目架构分析与Kafka迁移指南.md:213](../docs/项目架构分析与Kafka迁移指南.md#L213)
- **相关代码**: `Common/Database/SqliteConnection.py`

#### 🔍 问题描述
当前数据库操作没有事务支持，多个相关操作如果中间失败，可能导致数据不一致。

**风险示例**:
```python
# 操作 1: 更新充电会话状态
db.execute("UPDATE charging_sessions SET status='COMPLETED' WHERE id=?", (session_id,))

# ⚠️ 如果这里发生异常，会话已更新但 CP 状态未更新 -> 数据不一致

# 操作 2: 更新充电点状态
db.execute("UPDATE charging_points SET status='ACTIVE' WHERE id=?", (cp_id,))
```

#### ⚠️ 风险
- **数据不一致**: 部分操作成功，部分失败
- **并发问题**: 多个线程同时修改数据
- **回滚困难**: 出错后难以恢复

#### 💡 解决方案

**步骤 1: 在 SqliteConnection 添加事务支持**

```python
# 文件: Common/Database/SqliteConnection.py

import contextlib
import threading
from typing import Optional


class SqliteConnection:
    """SQLite 数据库连接管理（支持事务）"""

    def __init__(self, db_path, logger=None):
        self.db_path = db_path
        self.logger = logger
        self.conn = None
        self.lock = threading.RLock()  # 使用递归锁支持嵌套

    def get_connection(self):
        """获取数据库连接"""
        if not self.conn:
            import sqlite3
            self.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level=None  # 自动提交模式，事务由我们手动控制
            )
            self.conn.row_factory = sqlite3.Row  # 支持字典式访问
        return self.conn

    @contextlib.contextmanager
    def transaction(self, immediate=False):
        """
        事务上下文管理器

        用法:
            with db.transaction():
                cursor = db.get_connection().cursor()
                cursor.execute("UPDATE ...")
                cursor.execute("UPDATE ...")
                # 自动 commit，出错自动 rollback

        Args:
            immediate: 是否使用 IMMEDIATE 事务（默认 DEFERRED）
                      IMMEDIATE 会立即获取写锁，避免并发冲突

        Raises:
            任何在事务中发生的异常都会导致回滚并重新抛出
        """
        conn = self.get_connection()

        with self.lock:
            try:
                # 开始事务
                if immediate:
                    conn.execute("BEGIN IMMEDIATE")
                else:
                    conn.execute("BEGIN")

                if self.logger:
                    self.logger.debug("Transaction started")

                # 执行事务内容
                yield conn

                # 提交事务
                conn.commit()

                if self.logger:
                    self.logger.debug("Transaction committed")

            except Exception as e:
                # 回滚事务
                conn.rollback()

                if self.logger:
                    self.logger.error(f"Transaction failed, rolled back: {e}")

                # 重新抛出异常
                raise

    @contextlib.contextmanager
    def savepoint(self, name="sp"):
        """
        保存点（嵌套事务）

        用法:
            with db.transaction():
                cursor.execute("UPDATE table1 ...")

                try:
                    with db.savepoint():
                        cursor.execute("UPDATE table2 ...")  # 可能失败
                except:
                    pass  # table2 更新回滚，但 table1 更新保留

                # 外层事务继续
        """
        conn = self.get_connection()

        try:
            conn.execute(f"SAVEPOINT {name}")
            if self.logger:
                self.logger.debug(f"Savepoint '{name}' created")

            yield conn

            conn.execute(f"RELEASE SAVEPOINT {name}")
            if self.logger:
                self.logger.debug(f"Savepoint '{name}' released")

        except Exception as e:
            conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
            if self.logger:
                self.logger.warning(f"Rolled back to savepoint '{name}': {e}")
            raise

    def execute_in_transaction(self, func, *args, **kwargs):
        """
        在事务中执行函数（装饰器式用法）

        用法:
            def update_multiple_tables(db_conn):
                cursor = db_conn.cursor()
                cursor.execute("UPDATE ...")
                cursor.execute("UPDATE ...")

            db.execute_in_transaction(update_multiple_tables)
        """
        with self.transaction() as conn:
            return func(conn, *args, **kwargs)

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
            if self.logger:
                self.logger.info("Database connection closed")
```

**步骤 2: 修改业务代码使用事务**

```python
# 文件: Core/Central/ChargingPointManager.py

def complete_charging_session_and_update_cp(self, session_id, cp_id, energy_consumed, total_cost):
    """
    完成充电会话并更新充电点状态（事务版本）

    这两个操作必须原子性执行：
    1. 更新充电会话为 COMPLETED
    2. 更新充电点状态为 ACTIVE
    """
    try:
        # ✅ 使用事务确保原子性
        with self.charging_session_db.transaction(immediate=True):
            conn = self.charging_session_db.get_connection()
            cursor = conn.cursor()

            # 操作 1: 更新充电会话
            cursor.execute(
                """
                UPDATE charging_sessions
                SET status = ?,
                    end_time = ?,
                    energy_consumed_kwh = ?,
                    total_cost = ?
                WHERE session_id = ?
                """,
                ("COMPLETED", int(time.time()), energy_consumed, total_cost, session_id)
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Session {session_id} not found")

            # 操作 2: 更新充电点状态
            cursor.execute(
                """
                UPDATE charging_points
                SET status = ?,
                    current_session_id = NULL
                WHERE id = ?
                """,
                (Status.ACTIVE.value, cp_id)
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Charging point {cp_id} not found")

            self.logger.info(
                f"✅ Completed session {session_id} and updated CP {cp_id} (atomic)"
            )

            # 事务自动提交
            return True

    except Exception as e:
        # 事务自动回滚
        self.logger.error(
            f"❌ Failed to complete session and update CP: {e}",
            exc_info=True
        )
        return False

def assign_charging_point_to_driver(self, cp_id, driver_id, session_id):
    """
    分配充电点给司机（事务版本）

    原子操作：
    1. 更新充电点状态为 CHARGING
    2. 创建充电会话记录
    3. 更新充电点的当前会话ID
    """
    try:
        with self.charging_point_db.transaction(immediate=True):
            conn = self.charging_point_db.get_connection()
            cursor = conn.cursor()

            # 1. 检查充电点是否可用（加锁）
            cursor.execute(
                "SELECT status FROM charging_points WHERE id = ?",
                (cp_id,)
            )
            result = cursor.fetchone()

            if not result:
                raise ValueError(f"Charging point {cp_id} not found")

            if result['status'] != Status.ACTIVE.value:
                raise ValueError(
                    f"Charging point {cp_id} is not ACTIVE (current: {result['status']})"
                )

            # 2. 更新充电点状态
            cursor.execute(
                """
                UPDATE charging_points
                SET status = ?,
                    current_session_id = ?
                WHERE id = ?
                """,
                (Status.CHARGING.value, session_id, cp_id)
            )

            # 3. 创建充电会话
            cursor.execute(
                """
                INSERT INTO charging_sessions
                (session_id, cp_id, driver_id, start_time, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, cp_id, driver_id, int(time.time()), "ACTIVE")
            )

            self.logger.info(
                f"✅ Assigned CP {cp_id} to driver {driver_id} "
                f"(session: {session_id})"
            )

            return True

    except Exception as e:
        self.logger.error(
            f"❌ Failed to assign CP: {e}",
            exc_info=True
        )
        return False
```

**步骤 3: 使用保存点处理嵌套事务**

```python
# 文件: Core/Central/ChargingPointManager.py

def batch_update_charging_points_with_partial_failure_handling(self, updates):
    """
    批量更新充电点，支持部分失败

    使用保存点实现：某些更新失败不影响其他更新

    Args:
        updates: [(cp_id, new_status), ...]

    Returns:
        (成功数量, 失败数量, 失败详情)
    """
    success_count = 0
    failure_count = 0
    failures = []

    try:
        with self.charging_point_db.transaction():
            conn = self.charging_point_db.get_connection()
            cursor = conn.cursor()

            for cp_id, new_status in updates:
                try:
                    # 使用保存点
                    with self.charging_point_db.savepoint(f"update_{cp_id}"):
                        cursor.execute(
                            "UPDATE charging_points SET status = ? WHERE id = ?",
                            (new_status, cp_id)
                        )

                        if cursor.rowcount == 0:
                            raise ValueError(f"CP {cp_id} not found")

                        success_count += 1

                except Exception as e:
                    # 这个更新失败，但不影响其他更新
                    failure_count += 1
                    failures.append((cp_id, str(e)))
                    self.logger.warning(f"Failed to update CP {cp_id}: {e}")

            # 外层事务提交（包含所有成功的更新）
            self.logger.info(
                f"Batch update completed: {success_count} succeeded, "
                f"{failure_count} failed"
            )

    except Exception as e:
        # 外层事务失败，全部回滚
        self.logger.error(f"Batch update failed entirely: {e}")
        return (0, len(updates), [(cp_id, str(e)) for cp_id, _ in updates])

    return (success_count, failure_count, failures)
```

**步骤 4: 添加并发冲突重试机制**

```python
# 文件: Common/Database/TransactionHelper.py

"""
事务辅助工具

提供重试、死锁处理等高级功能
"""

import time
import sqlite3
from functools import wraps


def retry_on_locked(max_retries=3, delay=0.1):
    """
    装饰器：数据库锁定时自动重试

    SQLite 在并发写入时可能返回 SQLITE_BUSY
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)

                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e).lower():
                        last_exception = e
                        if attempt < max_retries - 1:
                            time.sleep(delay * (2 ** attempt))  # 指数退避
                            continue
                    raise

            raise last_exception

        return wrapper
    return decorator


# 使用示例
class ChargingPointManager:
    @retry_on_locked(max_retries=3, delay=0.1)
    def update_charging_point_with_retry(self, cp_id, new_status):
        """更新充电点状态（带重试）"""
        with self.charging_point_db.transaction(immediate=True):
            conn = self.charging_point_db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE charging_points SET status = ? WHERE id = ?",
                (new_status, cp_id)
            )
            return cursor.rowcount > 0
```

#### ✅ 验收标准
1. 所有关键业务操作都使用事务保护
2. 事务中发生异常能正确回滚
3. 保存点能正确处理嵌套事务
4. 并发写入不会导致数据不一致
5. 现有测试全部通过

#### ⏱️ 预估时间
- 实现事务框架: 1 小时
- 修改业务代码: 1-2 小时
- 测试验证: 1 小时
- **总计: 3-4 小时**

---

## 📅 实施计划

### Phase 1: 立即修复（第1-2天）

**优先级: 🔴 紧急**

| 任务 | 负责模块 | 预估时间 | 依赖 |
|-----|---------|---------|-----|
| TODO-3: 创建消息类型常量 | Common/Constants | 0.5h | 无 |
| TODO-3: 替换所有硬编码字符串 | 全局 | 1-2h | 上一步 |
| TODO-1: 实现认证功能 | Central + Monitor | 3-4h | TODO-3 |
| TODO-2: 修复线程停止机制 | Monitor | 2h | 无 |

**总计: 6.5-8.5 小时（约 1-2 个工作日）**

### Phase 2: 短期改进（第3-4天）

**优先级: 🟡 重要**

| 任务 | 负责模块 | 预估时间 | 依赖 |
|-----|---------|---------|-----|
| TODO-4: 实现维护通知 | Central | 1-3h | TODO-3 |
| TODO-5: Engine 超时处理 | Engine | 2h | TODO-2 |

**总计: 3-5 小时（约 0.5-1 个工作日）**

### Phase 3: 长期优化（第5-7天）

**优先级: 🟢 优化**

| 任务 | 负责模块 | 预估时间 | 依赖 |
|-----|---------|---------|-----|
| TODO-6: 数据库事务支持 | Database + 所有Manager | 3-4h | 无 |

**总计: 3-4 小时（约 0.5 个工作日）**

---

## 总工作量

- **总预估时间**: 12.5-17.5 小时
- **总工作日**: 2-3.5 天
- **建议排期**: 1 周（包含测试和文档）

---

## 🧪 测试建议

### 1. TODO-1 认证功能测试

```python
# tests/test_authentication.py

def test_auth_flow():
    """测试完整认证流程"""
    # 1. Monitor 连接到 Central
    # 2. Monitor 发送注册请求
    # 3. Monitor 收到注册确认
    # 4. Monitor 自动发送认证请求
    # 5. Central 验证并返回认证响应
    # 6. Monitor 收到认证成功
    pass

def test_auth_without_registration():
    """测试未注册直接认证（应该失败）"""
    pass

def test_auth_invalid_cp_id():
    """测试无效 CP ID 格式"""
    pass
```

### 2. TODO-2 线程停止测试

```python
# tests/test_thread_management.py

def test_graceful_thread_stop():
    """测试线程优雅停止"""
    monitor = Monitor(...)
    monitor.start()

    time.sleep(5)

    stop_time = time.time()
    monitor.stop()
    elapsed = time.time() - stop_time

    # 应该在 5 秒内停止
    assert elapsed < 5.0
    assert not monitor._heartbeat_thread.is_alive()
    assert not monitor._engine_health_thread.is_alive()
```

### 3. TODO-3 常量使用测试

```python
# tests/test_message_constants.py

def test_all_message_types_used():
    """确保所有消息类型都使用常量"""
    # 扫描代码，查找硬编码的 "type": "xxx"
    # 确保没有遗漏
    pass

def test_message_type_validity():
    """测试消息类型有效性检查"""
    assert MessageTypes.is_valid("register_request")
    assert not MessageTypes.is_valid("invalid_type")
```

### 4. TODO-6 事务测试

```python
# tests/test_database_transactions.py

def test_transaction_commit():
    """测试事务正常提交"""
    with db.transaction():
        cursor = db.get_connection().cursor()
        cursor.execute("INSERT INTO test_table VALUES (?)", (1,))

    # 验证数据已提交
    assert db.get_connection().execute("SELECT * FROM test_table").fetchone()

def test_transaction_rollback():
    """测试事务回滚"""
    try:
        with db.transaction():
            cursor = db.get_connection().cursor()
            cursor.execute("INSERT INTO test_table VALUES (?)", (1,))
            raise Exception("Simulated error")
    except:
        pass

    # 验证数据已回滚
    assert db.get_connection().execute("SELECT * FROM test_table").fetchone() is None

def test_concurrent_transactions():
    """测试并发事务"""
    # 启动多个线程同时写入
    # 验证数据一致性
    pass
```

---

## 📝 其他建议

### 1. 代码审查检查清单

在实施每个 TODO 后，进行以下检查：

- [ ] 代码是否遵循项目编码规范
- [ ] 是否添加了充分的注释和文档字符串
- [ ] 是否更新了相关文档（MESSAGE_FLOW_DOCUMENTATION.md 等）
- [ ] 是否添加了单元测试
- [ ] 日志输出是否清晰明确
- [ ] 异常处理是否完善
- [ ] 是否存在资源泄漏风险

### 2. 性能考虑

- **TODO-6 事务**: 注意事务粒度，避免长事务阻塞
- **TODO-2 线程**: 使用 Event.wait() 而非 sleep() 提高响应速度
- **TODO-5 超时检查**: 避免频繁检查，使用合理的检查间隔

### 3. 向后兼容

- **TODO-3 常量**: 实施时确保不破坏现有消息格式
- **TODO-1 认证**: 可以先设为可选功能，逐步迁移

### 4. 监控和告警

实施完成后，建议添加：
- 认证失败率监控
- 线程异常退出告警
- 数据库事务冲突统计
- 维护通知发送成功率

---

## 📚 相关文档

- [MESSAGE_FLOW_DOCUMENTATION.md](../MESSAGE_FLOW_DOCUMENTATION.md) - 消息流程文档
- [项目架构分析与Kafka迁移指南.md](../docs/项目架构分析与Kafka迁移指南.md) - 架构分析
- [TESTING_GUIDE.md](../TESTING_GUIDE.md) - 测试指南

---

## 📞 联系方式

如有疑问或需要讨论，请联系：
- 项目负责人: [填写]
- 技术支持: [填写]

---

**文档版本**: v1.0
**最后更新**: 2025-11-03
**维护者**: Claude Code Assistant
