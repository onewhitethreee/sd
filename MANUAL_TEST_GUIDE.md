# 手动测试指南

## 测试前准备

### 1. 环境检查
确保以下服务已启动：
- Kafka服务 (docker-compose up -d)
- 数据库文件存在 (ev_central.db)

### 2. 测试文件准备
确保以下文件存在：
- `test_services.txt` - 司机测试服务文件
- 所有Python模块文件完整

## 手动测试步骤

### 步骤1: 启动中央系统
```bash
# 在终端1中启动Central
python Core/Central/EV_Central.py 5000 localhost:9092
```

**预期结果**:
- 显示"EV Central started on port 5000"
- 显示数据库初始化成功
- 显示"Socket server initialized successfully"
- 显示"All systems initialized successfully"

### 步骤2: 启动充电点监控
```bash
# 在终端2中启动Monitor
python Charging_point/Monitor/EC_CP_M.py localhost:6000 localhost:5000 cp_001
```

**预期结果**:
- 显示"Starting EV_CP_M module"
- 显示"Connected to EV_Central"
- 显示"Registration message sent to central"
- 显示"Connected to EV_CP_E"
- 显示"Starting health check thread for EV_CP_E"

### 步骤3: 启动充电点引擎
```bash
# 在终端3中启动Engine
python Charging_point/Engine/EV_CP_E.py localhost:9092
```

**预期结果**:
- 显示"Starting EV_CP_E module"
- 显示"Monitor server started on localhost:6000"
- 显示"Connected to broker at localhost:9092"

### 步骤4: 验证充电点注册
在Central终端中应该看到：
- 充电点注册成功消息
- 充电点状态从DISCONNECTED变为ACTIVE
- 心跳消息每30秒接收一次

### 步骤5: 启动司机应用
```bash
# 在终端4中启动Driver
python Driver/EV_Driver.py localhost:9092 driver_001
```

**预期结果**:
- 显示"Starting Driver module"
- 显示"Connecting to Broker at localhost:9092"
- 显示"Client ID: driver_001"

### 步骤6: 发送充电请求
在Driver终端中：
1. 输入充电点ID (例如: cp_001)
2. 观察Central和Monitor的响应

**预期结果**:
- Central显示充电请求处理
- 充电点状态变为CHARGING
- 创建充电会话
- Driver收到授权通知

### 步骤7: 模拟充电过程
在Engine终端中：
1. 按任意键模拟开始充电
2. 观察实时数据更新

**预期结果**:
- 充电数据每秒更新
- Central显示实时监控信息
- Driver显示充电状态

### 步骤8: 完成充电
在Engine终端中：
1. 按任意键模拟结束充电
2. 观察充电完成流程

**预期结果**:
- 充电会话状态更新为completed
- 充电点状态恢复为ACTIVE
- Driver收到最终账单

### 步骤9: 测试故障处理
在Engine终端中：
1. 按Ctrl+C停止Engine
2. 观察Monitor的故障检测

**预期结果**:
- Monitor检测到Engine故障
- 发送故障通知到Central
- 充电点状态变为FAULTY

### 步骤10: 测试故障恢复
1. 重新启动Engine
2. 观察自动恢复过程

**预期结果**:
- Monitor重新连接到Engine
- 充电点状态恢复为ACTIVE
- 系统恢复正常运行

## 多充电点测试

### 启动多个充电点
```bash
# 终端5 - 第二个充电点
python Charging_point/Monitor/EC_CP_M.py localhost:6001 localhost:5000 cp_002
python Charging_point/Engine/EV_CP_E.py localhost:9092

# 终端6 - 第三个充电点
python Charging_point/Monitor/EC_CP_M.py localhost:6002 localhost:5000 cp_003
python Charging_point/Engine/EV_CP_E.py localhost:9092
```

### 测试并发充电请求
1. 同时从多个Driver发送充电请求
2. 观察系统处理并发请求的能力

## 性能测试

### 长时间运行测试
1. 让系统运行24小时
2. 观察内存使用情况
3. 检查是否有内存泄漏

### 高负载测试
1. 启动10个充电点
2. 同时发送100个充电请求
3. 观察系统响应时间

## 故障模拟测试

### 网络断开测试
1. 断开网络连接
2. 观察重连机制
3. 恢复网络连接
4. 验证自动恢复

### 数据库故障测试
1. 删除数据库文件
2. 观察系统行为
3. 重新创建数据库
4. 验证系统恢复

## 测试检查清单

### 功能测试
- [ ] 系统启动正常
- [ ] 充电点注册成功
- [ ] 心跳机制正常
- [ ] 充电请求处理正确
- [ ] 充电过程监控正常
- [ ] 充电完成流程正确
- [ ] 故障检测及时
- [ ] 故障恢复自动

### 性能测试
- [ ] 响应时间合理
- [ ] 内存使用稳定
- [ ] 并发处理正常
- [ ] 长时间运行稳定

### 安全测试
- [ ] 故障时安全停止
- [ ] 数据一致性保证
- [ ] 网络断开处理
- [ ] 异常情况处理

## 常见问题排查

### 问题1: Central无法启动
**可能原因**:
- 端口5000被占用
- 数据库文件权限问题

**解决方法**:
- 检查端口占用: `netstat -an | grep 5000`
- 检查文件权限: `ls -la ev_central.db`

### 问题2: 充电点无法注册
**可能原因**:
- Central未启动
- 网络连接问题
- 配置参数错误

**解决方法**:
- 确认Central已启动
- 检查网络连接
- 验证配置参数

### 问题3: 心跳消息丢失
**可能原因**:
- 网络延迟
- 系统负载过高
- 超时设置过短

**解决方法**:
- 检查网络状况
- 监控系统资源
- 调整超时设置

## 测试报告模板

### 测试环境
- 操作系统: 
- Python版本: 
- 测试时间: 
- 测试人员: 

### 测试结果
| 测试项目 | 预期结果 | 实际结果 | 状态 |
|---------|---------|---------|------|
| 系统启动 | 正常启动 | | |
| 充电点注册 | 注册成功 | | |
| 充电请求 | 处理正确 | | |
| 故障处理 | 检测及时 | | |
| 性能测试 | 响应正常 | | |

### 问题记录
| 问题描述 | 严重程度 | 状态 | 备注 |
|---------|---------|------|------|
| | | | |

### 测试结论
- 系统功能完整性: 
- 系统稳定性: 
- 系统性能: 
- 总体评价: 
