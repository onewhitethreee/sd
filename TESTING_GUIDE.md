# 重构后测试指南

## 🎯 测试目标

验证重构后的 Engine 和 Monitor MessageDispatcher 是否正常工作，特别是：
1. ✅ `command_response` 处理器不再产生 warning
2. ✅ 所有消息正常发送和接收
3. ✅ 完整的充电流程正常运行

---

## 🚀 快速测试步骤

### 步骤1: 启动系统组件

按以下顺序启动组件：

```bash
# 1. 启动 Engine (Terminal 1)
cd Charging_point/Engine
python EV_CP_E.py 0.0.0.0:0

# 记录 Engine 的实际监听地址，例如: 127.0.0.1:54321

# 2. 启动 Central (Terminal 2)
cd Core/Central
python EV_Central.py 0.0.0.0:5000

# 3. 启动 Monitor (Terminal 3)
cd Charging_point/Monitor
python EC_CP_M.py 127.0.0.1:54321 127.0.0.1:5000 CP001

# 4. 启动 Driver (Terminal 4)
cd Driver
python EV_Driver.py 127.0.0.1:5000 DRIVER001
```

### 步骤2: 观察启动日志

#### ✅ 期望看到的日志

**Engine 日志**:
```
INFO: Monitor server started on 127.0.0.1:54321
INFO: Engine status: ACTIVE
```

**Monitor 日志**:
```
INFO: Connected to Engine successfully
INFO: Received registration response from Central: {'status': 'success', ...}
INFO: Registration successful.
INFO: Charging point status updated: ACTIVE
DEBUG: Health check response from Engine: {'type': 'health_check_response', ...}
```

**Central 日志**:
```
INFO: Charging Point CP001 registered successfully
INFO: Received heartbeat from CP001, status: ACTIVE
```

#### ❌ 不应该看到的 warning

**重构前会出现的 warning**:
```
WARNING: Unknown message type from Engine: command_response  # ← 这个不应该出现了！
```

**如果看到这个 warning，说明重构失败**。

---

### 步骤3: 测试充电流程

#### 在 Driver CLI 中执行：

```bash
# 1. 查看可用充电点
> list

# 期望输出:
Available Charging Points:
- CP001 (Status: ACTIVE)

# 2. 请求充电
> charge CP001

# 期望输出:
Charging request sent for CP001
Charging started successfully at CP001
Session ID: xxxxx-xxxxx-xxxxx
```

#### 观察各组件日志

**Monitor 应该输出**:
```
INFO: Received start charging command from Central.
DEBUG: Start charging command sent to Engine for session xxxxx
DEBUG: Engine命令执行成功: Charging started (session: xxxxx)  # ← 关键！不应该有 warning
```

**Engine 应该输出**:
```
INFO: Processing start charging command
INFO: Starting charging session xxxxx
INFO: Charging session started successfully
INFO: Sending charging data...
```

**Central 应该输出**:
```
INFO: Received charge request from DRIVER001 for CP001
INFO: Sending start charging command to CP001
INFO: Received charging data from CP001
```

**Driver 应该输出**:
```
Charging in progress: 1.5 kWh, Cost: €0.38
Charging in progress: 3.2 kWh, Cost: €0.80
...
```

---

### 步骤4: 测试停止充电

#### 在 Driver CLI 中执行：

```bash
> stop CP001

# 期望输出:
Stop charging request sent for CP001
Charging stopped successfully
```

#### 观察 Monitor 日志

**关键日志**:
```
INFO: Received stop charging command from Central.
INFO: 停止充电命令已转发给Engine: CP xxxxx, Session xxxxx
DEBUG: Engine命令执行成功: Charging stopped (session: xxxxx)  # ← 关键！应该正常处理
```

**不应该出现**:
```
WARNING: Unknown message type from Engine: command_response  # ← 不应该出现
```

---

## ✅ 测试检查清单

### 基础功能测试

- [ ] Engine 成功启动并监听
- [ ] Monitor 成功连接 Engine
- [ ] Monitor 成功注册到 Central
- [ ] Health check 正常工作（每30秒）
- [ ] Heartbeat 正常工作（每30秒）

### 消息处理测试

- [ ] **command_response 不再产生 warning** ⭐ 重点
- [ ] register_response 正常处理
- [ ] heartbeat_response 正常处理
- [ ] start_charging_command 正常转发
- [ ] stop_charging_command 正常转发
- [ ] charging_data 正常转发
- [ ] charge_completion 正常转发

### 充电流程测试

- [ ] Driver 可以查看可用充电点
- [ ] Driver 可以请求充电
- [ ] 充电命令正确传递到 Engine
- [ ] **Engine 的 command_response 被正确处理** ⭐ 重点
- [ ] 充电数据实时更新
- [ ] Driver 可以停止充电
- [ ] **停止命令的 command_response 被正确处理** ⭐ 重点
- [ ] 充电完成通知正常

### 状态管理测试

- [ ] Monitor 状态从 DISCONNECTED → ACTIVE
- [ ] Engine 故障时 Monitor 变为 FAULTY
- [ ] Central 断开时 Monitor 变为 FAULTY

---

## 🐛 常见问题排查

### 问题1: 仍然看到 "Unknown message type: command_response" warning

**可能原因**:
1. Monitor MessageDispatcher 没有正确重载
2. 代码没有保存
3. 使用了旧的 .pyc 缓存文件

**解决方案**:
```bash
# 清除 Python 缓存
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

# 重新启动 Monitor
python EC_CP_M.py 127.0.0.1:54321 127.0.0.1:5000 CP001
```

---

### 问题2: ModuleNotFoundError: No module named 'Common.Message.MessageTypes'

**可能原因**:
Python 路径设置问题

**解决方案**:
```bash
# 确保从项目根目录运行
cd d:\desktop\Universidad\4_cursor\1\SD\practica\2

# 或设置 PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

---

### 问题3: Engine 和 Monitor 连接失败

**可能原因**:
1. Engine 地址写错
2. 端口被占用
3. 防火墙阻止

**解决方案**:
```bash
# 检查 Engine 实际监听的端口
# Engine 启动时会显示:
# ENGINE LISTENING ON: 127.0.0.1:xxxxx

# 使用该地址启动 Monitor
python EC_CP_M.py 127.0.0.1:xxxxx 127.0.0.1:5000 CP001
```

---

## 📊 测试成功标准

### ✅ 全部通过标准

1. **无 warning 日志**
   - 不出现 "Unknown message type: command_response"
   - 不出现其他未知消息类型 warning

2. **消息流正常**
   - 所有消息正确发送和接收
   - 消息内容完整

3. **充电流程完整**
   - 可以成功开始充电
   - 可以看到充电进度
   - 可以成功停止充电

4. **状态管理正确**
   - Monitor 状态正确更新
   - 连接状态正确反映

5. **日志清晰**
   - 所有关键操作都有日志
   - 日志信息完整准确

---

## 🔬 深度测试（可选）

### 测试1: 命令失败场景

在 Engine 充电中时，尝试启动另一个充电会话：

**期望结果**:
- Engine 返回 `command_response` with status: "failure"
- Monitor 正确处理并记录 warning
- 不会产生 "Unknown message type" warning

### 测试2: Engine 断开重连

1. 启动完整系统
2. 停止 Engine (Ctrl+C)
3. Monitor 应该检测到连接丢失
4. 重新启动 Engine
5. Monitor 应该自动重连

**期望结果**:
- 所有消息处理正常恢复
- 无 warning 日志

### 测试3: 并发充电请求

启动多个 Driver，同时请求充电：

```bash
# Terminal 5
python EV_Driver.py 127.0.0.1:5000 DRIVER002

# Terminal 6
python EV_Driver.py 127.0.0.1:5000 DRIVER003
```

**期望结果**:
- 只有一个充电请求成功
- 其他请求收到正确的错误响应
- 所有 command_response 正确处理

---

## 📝 测试报告模板

### 测试日期: ___________
### 测试人员: ___________

#### 基础功能
- [ ] 系统启动正常
- [ ] 组件连接正常
- [ ] Health check 正常
- [ ] Heartbeat 正常

#### 关键验证点
- [ ] **command_response 不再产生 warning** ⭐
- [ ] 充电流程完整
- [ ] 状态管理正确

#### 发现的问题
1. _________________________
2. _________________________
3. _________________________

#### 测试结论
- [ ] ✅ 通过：所有功能正常，无 warning
- [ ] ⚠️ 部分通过：部分功能正常
- [ ] ❌ 失败：关键功能异常

#### 备注
_________________________
_________________________

---

## 🎉 测试通过后

恭喜！重构成功完成。

### 下一步行动

1. **提交代码**
   ```bash
   git add .
   git commit -m "refactor: 重构Engine和Monitor MessageDispatcher，统一使用消息常量"
   ```

2. **更新文档**
   - 确认 MESSAGE_FLOW_DOCUMENTATION.md 准确
   - 更新团队使用指南

3. **计划下一阶段重构**
   - Central MessageDispatcher
   - Driver MessageDispatcher
   - 消息发送代码统一

---

**测试愉快！** 🚀
