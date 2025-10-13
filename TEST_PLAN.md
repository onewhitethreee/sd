# 电动汽车充电系统测试计划

## 测试环境准备

### 1. 启动顺序
```bash
# 1. 启动Kafka服务
docker-compose up -d

# 2. 启动中央系统 (EV_Central)
python Core/Central/EV_Central.py 5000 localhost:9092

# 3. 启动充电点监控 (EV_CP_M)
python Charging_point/Monitor/EC_CP_M.py localhost:6000 localhost:5000 cp_001

# 4. 启动充电点引擎 (EV_CP_E)
python Charging_point/Engine/EV_CP_E.py localhost:9092

# 5. 启动司机应用 (EV_Driver)
python Driver/EV_Driver.py localhost:9092 driver_001
```

### 2. 测试文件准备
创建司机测试文件 `test_services.txt`:
```
cp_001
cp_002
cp_001
```

## 测试用例

### 测试用例1: 系统启动和初始化
**目标**: 验证系统各组件能正常启动并建立连接

**步骤**:
1. 启动EV_Central，验证监听端口5000
2. 启动EV_CP_M，验证连接到Central和Engine
3. 启动EV_CP_E，验证Engine服务启动
4. 验证充电点注册到Central

**预期结果**:
- Central显示充电点注册成功
- 充电点状态为DISCONNECTED（初始状态）
- 所有组件日志显示连接成功

### 测试用例2: 充电点注册和心跳
**目标**: 验证充电点能正确注册并发送心跳

**步骤**:
1. 启动所有组件
2. 观察Central面板显示充电点信息
3. 验证心跳消息每30秒发送一次
4. 验证充电点状态更新为ACTIVE

**预期结果**:
- 充电点成功注册到Central
- 心跳消息正常发送和接收
- 充电点状态从DISCONNECTED变为ACTIVE

### 测试用例3: 充电请求流程
**目标**: 验证完整的充电请求和授权流程

**步骤**:
1. 司机发送充电请求到Central
2. Central验证充电点可用性
3. Central授权充电请求
4. 创建充电会话
5. 通知充电点和司机

**预期结果**:
- 充电请求被正确验证
- 充电会话成功创建
- 充电点状态变为CHARGING
- 司机收到授权通知

### 测试用例4: 充电过程监控
**目标**: 验证充电过程中的实时监控

**步骤**:
1. 开始充电会话
2. 模拟充电过程（每秒发送数据）
3. 验证Central显示实时数据
4. 验证司机应用显示充电状态

**预期结果**:
- 实时数据正确显示
- 电量消耗和费用计算正确
- 所有界面同步更新

### 测试用例5: 充电完成流程
**目标**: 验证充电完成和会话结束

**步骤**:
1. 完成充电会话
2. 发送充电完成通知
3. 更新充电会话状态
4. 充电点返回ACTIVE状态

**预期结果**:
- 充电会话状态更新为completed
- 充电点状态恢复为ACTIVE
- 司机收到最终账单

### 测试用例6: 故障检测和处理
**目标**: 验证故障检测和自动恢复机制

**步骤**:
1. 模拟Engine故障（按任意键）
2. 验证Monitor检测到故障
3. 验证故障报告发送到Central
4. 验证充电点状态变为FAULTY
5. 模拟故障恢复
6. 验证自动恢复机制

**预期结果**:
- 故障被及时检测
- 故障状态正确报告
- 系统进入安全模式
- 故障恢复后自动恢复正常

### 测试用例7: 多充电点并发测试
**目标**: 验证系统支持多个充电点并发操作

**步骤**:
1. 启动多个充电点实例
2. 同时发送多个充电请求
3. 验证系统正确处理并发请求
4. 验证数据库一致性

**预期结果**:
- 多个充电点正常注册
- 并发请求正确处理
- 数据库状态一致

### 测试用例8: 网络断开重连测试
**目标**: 验证网络断开后的重连机制

**步骤**:
1. 正常启动系统
2. 模拟网络断开
3. 验证重连机制启动
4. 恢复网络连接
5. 验证系统自动恢复

**预期结果**:
- 网络断开被检测
- 重连机制正常工作
- 系统自动恢复服务

## 自动化测试脚本

### 测试脚本1: 基础功能测试
```python
# test_basic_functionality.py
import subprocess
import time
import requests

def test_central_startup():
    """测试中央系统启动"""
    pass

def test_cp_registration():
    """测试充电点注册"""
    pass

def test_charging_request():
    """测试充电请求"""
    pass
```

### 测试脚本2: 故障处理测试
```python
# test_fault_handling.py
def test_engine_fault():
    """测试引擎故障"""
    pass

def test_network_disconnect():
    """测试网络断开"""
    pass

def test_auto_recovery():
    """测试自动恢复"""
    pass
```

## 性能测试

### 负载测试
- 同时处理100个充电请求
- 验证系统响应时间
- 验证内存使用情况

### 压力测试
- 连续运行24小时
- 验证系统稳定性
- 验证数据库性能

## 测试数据

### 测试充电点配置
```
CP_ID: cp_001, cp_002, cp_003
Location: "Test Location 1", "Test Location 2", "Test Location 3"
Price: 0.20, 0.25, 0.30 (EUR/kWh)
```

### 测试司机配置
```
Driver_ID: driver_001, driver_002, driver_003
Username: "Test Driver 1", "Test Driver 2", "Test Driver 3"
```

## 测试报告模板

### 测试结果记录
- 测试用例名称
- 执行时间
- 测试结果（通过/失败）
- 错误信息（如有）
- 性能指标

### 问题跟踪
- 问题描述
- 重现步骤
- 严重程度
- 修复状态
