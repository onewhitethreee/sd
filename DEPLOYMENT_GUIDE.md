# EV Charging System - 部署指南

## 📋 目录

1. [环境要求](#环境要求)
2. [安装步骤](#安装步骤)
3. [配置说明](#配置说明)
4. [单机部署](#单机部署)
5. [分布式部署](#分布式部署)
6. [Docker部署](#docker部署)
7. [验证与测试](#验证与测试)
8. [故障排除](#故障排除)

---

## 环境要求

### 系统要求

- **操作系统**: Windows 10/11, Linux, macOS
- **Python版本**: Python 3.8 或更高版本
- **内存**: 最低 2GB RAM（推荐 4GB+）
- **磁盘空间**: 至少 500MB 可用空间

### 必需软件

1. **Python 3.8+**
   ```bash
   # 检查Python版本
   python --version
   # 或
   python3 --version
   ```

2. **Apache Kafka**
   - 版本: 2.8+ (推荐使用 Docker 部署)
   - 注意: 新版本 Kafka (3.0+) 不需要 Zookeeper

3. **SQLite3**
   - 通常随 Python 一起安装
   - 无需额外安装

4. **Docker** (可选，用于快速启动 Kafka)
   - Docker Desktop 或 Docker Engine

---

## 安装步骤

### 步骤 1: 克隆或下载项目

```bash
# 如果使用Git
git clone <repository-url>
cd practica/2

# 或直接解压项目文件到目标目录
```

### 步骤 2: 安装 Python 依赖

```bash
# 进入项目根目录
cd D:\desktop\Universidad\4_cursor\1\SD\practica\2

# 安装依赖包
pip install -r requirements.txt

# 或使用虚拟环境（推荐）
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

**依赖包列表**:
- `colorama==0.4.6` - 终端颜色支持
- `colorlog==6.9.0` - 彩色日志
- `kafka-python==2.2.15` - Kafka客户端
- `python-dotenv==1.2.1` - 环境变量管理
- `rich==13.7.0` - 美化CLI输出

### 步骤 3: 启动 Kafka

#### 选项 A: 使用 Docker (推荐)

```bash
# 启动Kafka容器
docker-compose up -d

# 查看Kafka状态
docker-compose ps

# 查看日志
docker-compose logs -f broker
```

#### 选项 B: 手动安装 Kafka

1. 下载 Kafka: https://kafka.apache.org/downloads
2. 解压到目录，例如: `C:\kafka`
3. 启动 Kafka:
   ```bash
   # Windows
   cd C:\kafka
   .\bin\windows\kafka-server-start.bat .\config\server.properties
   
   # Linux/macOS
   cd /path/to/kafka
   bin/kafka-server-start.sh config/server.properties
   ```

#### 验证 Kafka 运行

```bash
# 使用Docker时
docker exec -it broker kafka-topics.sh --bootstrap-server localhost:9092 --list

# 或手动安装时
kafka-topics.sh --bootstrap-server localhost:9092 --list
```

### 步骤 4: 创建配置文件 (可选)

创建 `.env` 文件（可选，用于开发模式）:

```bash
# 在项目根目录创建 .env 文件
# .env 文件示例:

# 调试模式 (true/false)
DEBUG_MODE=False

# Kafka Broker地址
BROKER_ADDRESS=localhost:9092

# Central监听端口
LISTEN_PORT=5000

# 数据库路径
DB_PATH=ev_central.db

# Engine监听地址 (开发模式)
IP_PORT_EV_CP_E=localhost:6000

# Central地址 (开发模式)
IP_PORT_EV_CP_CENTRAL=localhost:5000

# 最大充电时长（秒）
MAX_CHARGING_DURATION=30
```

**注意**: 
- 如果 `DEBUG_MODE=False`，必须通过命令行参数启动
- 如果 `DEBUG_MODE=True`，可以使用配置文件中的默认值

---

## 配置说明

### 命令行参数

#### EV_Central (中央控制器)

```bash
python Core/Central/EV_Central.py <listen_port> <broker_address>

# 参数说明:
# listen_port: Central监听端口 (例如: 5000)
# broker_address: Kafka Broker地址 (格式: IP:PORT, 例如: localhost:9092)

# 示例:
python Core/Central/EV_Central.py 5000 localhost:9092
```

#### EV_CP_E (充电桩引擎)

```bash
python Charging_point/Engine/EV_CP_E.py <broker_address> [--debug_port PORT]

# 参数说明:
# broker_address: Kafka Broker地址 (格式: IP:PORT)
# --debug_port: (可选) 指定Engine监听端口，用于开发模式

# 示例:
python Charging_point/Engine/EV_CP_E.py localhost:9092
python Charging_point/Engine/EV_CP_E.py localhost:9092 --debug_port 5003
```

**注意**: 如果不指定 `--debug_port`，Engine会自动分配可用端口，并在启动时显示实际端口。

#### EC_CP_M (充电桩监控)

```bash
python Charging_point/Monitor/EC_CP_M.py <engine_address> <central_address> <cp_id>

# 参数说明:
# engine_address: Engine地址 (格式: IP:PORT)
# central_address: Central地址 (格式: IP:PORT)
# cp_id: 充电桩唯一标识符 (例如: cp_001)

# 示例:
python Charging_point/Monitor/EC_CP_M.py localhost:5003 localhost:5000 cp_001
```

#### EV_Driver (司机应用)

```bash
python Driver/EV_Driver.py <broker_address> <driver_id>

# 参数说明:
# broker_address: Kafka Broker地址 (格式: IP:PORT)
# driver_id: 司机唯一标识符 (例如: driver_001)

# 示例:
python Driver/EV_Driver.py localhost:9092 driver_001
```

---

## 单机部署

### 场景 1: 开发模式 (Debug Mode)

**适用场景**: 本地开发测试

1. **创建 `.env` 文件**:
   ```env
   DEBUG_MODE=True
   BROKER_ADDRESS=localhost:9092
   LISTEN_PORT=5000
   DB_PATH=ev_central.db
   IP_PORT_EV_CP_E=localhost:6000
   IP_PORT_EV_CP_CENTRAL=localhost:5000
   ```

2. **启动系统**:
   ```bash
   # Windows
   Common\tools\start_services_dev.bat
   
   # 或手动启动（按顺序）:
   # Terminal 1: Central
   python Core\Central\EV_Central.py
   
   # Terminal 2: Engine
   python Charging_point\Engine\EV_CP_E.py
   
   # Terminal 3: Monitor
   python Charging_point\Monitor\EC_CP_M.py
   
   # Terminal 4: Driver
   python Driver\EV_Driver.py
   ```

### 场景 2: 生产模式 (Production Mode)

**适用场景**: 演示或测试环境

1. **确保 `.env` 中 `DEBUG_MODE=False`** 或不创建 `.env` 文件

2. **启动系统**:
   ```bash
   # Windows - 使用批处理脚本
   Common\tools\start_services_production.bat
   
   # 或手动启动（按顺序）:
   
   # Terminal 1: 启动 Kafka (如果使用Docker)
   docker-compose up -d
   
   # Terminal 2: Central
   python Core\Central\EV_Central.py 5000 localhost:9092
   
   # Terminal 3: Engine (注意记录显示的端口)
   python Charging_point\Engine\EV_CP_E.py localhost:9092 --debug_port 5003
   # 输出示例: "ENGINE LISTENING ON: localhost:5003"
   
   # Terminal 4: Monitor (使用Engine的实际端口)
   python Charging_point\Monitor\EC_CP_M.py localhost:5003 localhost:5000 cp_001
   
   # Terminal 5: Driver
   python Driver\EV_Driver.py localhost:9092 driver_001
   ```

### 场景 3: 启动多个充电桩

```bash
# Windows
Common\tools\start_multi_charging_points.bat

# 或手动启动多个实例:
# Terminal 1: Engine 1
python Charging_point\Engine\EV_CP_E.py localhost:9092 --debug_port 5003

# Terminal 2: Monitor 1
python Charging_point\Monitor\EC_CP_M.py localhost:5003 localhost:5000 cp_001

# Terminal 3: Engine 2
python Charging_point\Engine\EV_CP_E.py localhost:9092 --debug_port 5004

# Terminal 4: Monitor 2
python Charging_point\Monitor\EC_CP_M.py localhost:5004 localhost:5000 cp_002
```

---

## 分布式部署

### 场景 1: 实验室多机部署 (推荐，最高分)

**架构**: 
- 机器A: Central + Kafka
- 机器B: CP1 (Monitor + Engine)
- 机器C: CP2 + Driver

#### 准备工作

1. **确保所有机器在同一网络**
2. **关闭防火墙或开放必要端口**:
   - Central监听端口: 5000 (默认)
   - Kafka端口: 9092
   - Engine端口: 动态分配

3. **测试网络连通性**:
   ```bash
   # 在机器B上测试连接到机器A
   ping <机器A的IP>
   telnet <机器A的IP> 5000
   telnet <机器A的IP> 9092
   ```

#### 部署步骤

**机器A (Central + Kafka)**:

```bash
# 1. 启动Kafka
docker-compose up -d

# 修改docker-compose.yml中的KAFKA_ADVERTISED_LISTENERS
# 从: PLAINTEXT://localhost:9092
# 改为: PLAINTEXT://<机器A的IP>:9092

# 2. 启动Central
python Core/Central/EV_Central.py 5000 0.0.0.0:9092
# 注意: 使用0.0.0.0允许远程连接
```

**机器B (CP1)**:

```bash
# 1. 启动Engine
python Charging_point/Engine/EV_CP_E.py <机器A的IP>:9092 --debug_port 5003

# 2. 启动Monitor (使用机器A的IP和Central端口)
python Charging_point/Monitor/EC_CP_M.py localhost:5003 <机器A的IP>:5000 cp_001
```

**机器C (CP2 + Driver)**:

```bash
# 1. 启动Engine
python Charging_point/Engine/EV_CP_E.py <机器A的IP>:9092 --debug_port 5003

# 2. 启动Monitor
python Charging_point/Monitor/EC_CP_M.py localhost:5003 <机器A的IP>:5000 cp_002

# 3. 启动Driver
python Driver/EV_Driver.py <机器A的IP>:9092 driver_001
```

### 场景 2: 多台笔记本组网

**注意事项**:
1. 确保所有笔记本在同一WiFi网络
2. 获取每台机器的IP地址:
   ```bash
   # Windows
   ipconfig
   
   # Linux/macOS
   ifconfig
   # 或
   ip addr
   ```
3. 配置防火墙允许连接
4. 使用静态IP或确保IP地址稳定

**部署步骤**: 同场景1，使用实际IP地址替换`<机器A的IP>`

### 场景 3: 虚拟机部署

**架构**:
- VM1: Central + Kafka
- VM2: CP1
- VM3: CP2 + Driver

**配置要点**:
1. 虚拟机网络模式: 桥接模式 (Bridged) 或 NAT
2. 确保虚拟机之间可以互相访问
3. 使用虚拟机IP地址进行配置

---

## Docker部署

### 使用 Docker Compose 部署完整系统

创建 `docker-compose-full.yml`:

```yaml
version: '3.8'

services:
  kafka:
    image: apache/kafka:latest
    container_name: kafka
    ports:
      - 9092:9092
      - 9093:9093
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_ID: 1
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_NUM_PARTITIONS: 3

  central:
    build:
      context: .
      dockerfile: Dockerfile.central
    depends_on:
      - kafka
    ports:
      - "5000:5000"
    environment:
      - BROKER_ADDRESS=kafka:9092
      - LISTEN_PORT=5000
      - DB_PATH=/app/ev_central.db
    volumes:
      - ./ev_central.db:/app/ev_central.db

  # 注意: Engine和Monitor需要特殊处理，因为它们需要动态端口分配
  # 建议在宿主机上运行，或使用host网络模式
```

**注意**: 由于 Engine 需要动态端口分配，建议在宿主机上运行 Engine 和 Monitor，只使用 Docker 部署 Kafka 和 Central。

---

## 验证与测试

### 启动验证清单

#### 1. 检查 Kafka 运行状态

```bash
# 查看Kafka topics
docker exec -it broker kafka-topics.sh --bootstrap-server localhost:9092 --list

# 应该看到以下topics（系统启动后自动创建）:
# - charging_session_data
# - charging_session_complete
# - driver_charge_requests
# - driver_stop_requests
# - driver_cps_requests
# - driver_responses
```

#### 2. 检查 Central 启动

查看 Central 日志，应该看到:
```
INFO: Socket server initialized successfully
INFO: Database initialized successfully
INFO: Kafka producer initialized successfully
INFO: Kafka consumers initialized successfully
INFO: Admin CLI initialized successfully
```

#### 3. 检查 Monitor 连接

查看 Monitor 日志，应该看到:
```
INFO: Connected to Engine successfully
INFO: Connected to Central successfully
INFO: Registration successful
INFO: Charging point status updated: ACTIVE
```

#### 4. 检查 Driver 连接

查看 Driver 日志，应该看到:
```
INFO: Kafka producer initialized successfully
INFO: Available charging points request sent
```

### 功能测试

#### 测试 1: 查询可用充电桩

在 Driver CLI 中:
```
> list
```

**期望输出**: 显示所有 ACTIVE 状态的充电桩

#### 测试 2: 请求充电

在 Driver CLI 中:
```
> charge cp_001
```

**期望输出**: 
- Driver显示充电请求已发送
- Monitor显示收到启动充电命令
- Engine开始充电过程
- Driver显示实时充电数据

#### 测试 3: 查看充电历史

在 Driver CLI 中:
```
> history
```

**期望输出**: 显示所有充电历史记录

#### 测试 4: Engine CLI 功能

在 Engine 窗口中按 `ENTER` 键，应该看到菜单:
```
[1] 模拟车辆接入
[2] 模拟车辆拔出
[3] 模拟Engine故障
[4] 模拟Engine恢复
[5] 显示当前状态
```

### 弹性测试

#### 测试 Monitor 崩溃恢复

1. 启动完整系统
2. 关闭 Monitor 窗口 (Ctrl+C)
3. **预期**: Central 将 CP 状态标记为 DISCONNECTED
4. 重启 Monitor
5. **预期**: CP 重新注册并恢复 ACTIVE 状态

#### 测试 Engine 崩溃恢复

1. 启动完整系统并开始充电
2. 关闭 Engine 窗口 (Ctrl+C)
3. **预期**: 
   - Monitor 检测到 Engine 无响应
   - Monitor 向 Central 报告故障
   - Central 将 CP 标记为 FAULTY
4. 重启 Engine
5. **预期**: CP 恢复 ACTIVE 状态

#### 测试 Engine CLI 故障模拟

1. 在 Engine 窗口中按 `ENTER`
2. 选择 `[3] 模拟Engine故障`
3. **预期**: 
   - Monitor 收到 KO 信号
   - Central 将 CP 标记为 FAULTY
4. 选择 `[4] 模拟Engine恢复`
5. **预期**: CP 恢复 ACTIVE 状态

---

## 故障排除

### 常见问题

#### 问题 1: Kafka 连接失败

**症状**: 
```
ERROR: Failed to initialize Kafka producer
ERROR: Kafka not connected
```

**解决方案**:
1. 检查 Kafka 是否运行:
   ```bash
   docker-compose ps
   # 或
   docker ps | grep kafka
   ```
2. 检查端口是否被占用:
   ```bash
   # Windows
   netstat -ano | findstr :9092
   
   # Linux/macOS
   lsof -i :9092
   ```
3. 检查防火墙设置
4. 验证 Broker 地址是否正确

#### 问题 2: Socket 连接失败

**症状**:
```
ERROR: Connection refused
ERROR: Failed to connect to Central
```

**解决方案**:
1. 检查 Central 是否正在运行
2. 检查端口是否正确:
   ```bash
   # Windows
   netstat -ano | findstr :5000
   
   # Linux/macOS
   lsof -i :5000
   ```
3. 检查防火墙是否阻止连接
4. 验证 IP 地址是否正确（分布式部署时）

#### 问题 3: Engine 端口冲突

**症状**:
```
ERROR: Address already in use
```

**解决方案**:
1. 使用 `--debug_port` 指定其他端口
2. 或让系统自动分配端口（不指定 `--debug_port`）

#### 问题 4: 数据库锁定错误

**症状**:
```
ERROR: database is locked
```

**解决方案**:
1. 确保只有一个 Central 实例在运行
2. 检查数据库文件权限
3. 删除数据库文件重新创建（注意: 会丢失数据）

#### 问题 5: 依赖包缺失

**症状**:
```
ModuleNotFoundError: No module named 'kafka'
```

**解决方案**:
```bash
pip install -r requirements.txt
```

### 日志查看

#### 查看组件日志

所有组件都会在控制台输出日志:
- **INFO**: 正常操作信息
- **DEBUG**: 调试信息（需要设置 `DEBUG_MODE=True`）
- **WARNING**: 警告信息
- **ERROR**: 错误信息

#### 日志级别调整

在代码中修改日志级别:
```python
# 在组件主文件中
logger = CustomLogger.get_logger(level=logging.INFO)  # 或 logging.DEBUG
```

### 网络诊断

#### 测试端口连通性

```bash
# Windows
telnet <IP> <PORT>

# Linux/macOS
nc -zv <IP> <PORT>
# 或
telnet <IP> <PORT>
```

#### 测试 Kafka 连通性

```bash
# 使用Kafka客户端测试
kafka-console-producer.sh --bootstrap-server <IP>:9092 --topic test
kafka-console-consumer.sh --bootstrap-server <IP>:9092 --topic test --from-beginning
```

---

## 部署检查清单

### 部署前检查

- [ ] Python 3.8+ 已安装
- [ ] 所有依赖包已安装 (`pip install -r requirements.txt`)
- [ ] Kafka 已启动并运行
- [ ] 防火墙已配置（分布式部署）
- [ ] 网络连通性已验证（分布式部署）
- [ ] 端口未被占用

### 部署后检查

- [ ] Central 成功启动
- [ ] Monitor 成功连接到 Central 和 Engine
- [ ] Engine 成功启动并监听
- [ ] Driver 成功连接到 Kafka
- [ ] 充电桩成功注册到 Central
- [ ] 可以查询可用充电桩
- [ ] 可以发起充电请求
- [ ] 充电过程正常
- [ ] 充电完成通知正常

---

## 快速参考

### 启动命令速查表

| 组件 | 命令 | 说明 |
|------|------|------|
| Kafka | `docker-compose up -d` | 使用Docker启动 |
| Central | `python Core/Central/EV_Central.py 5000 localhost:9092` | 监听5000端口 |
| Engine | `python Charging_point/Engine/EV_CP_E.py localhost:9092` | 自动分配端口 |
| Monitor | `python Charging_point/Monitor/EC_CP_M.py <engine_ip:port> <central_ip:port> <cp_id>` | 连接Engine和Central |
| Driver | `python Driver/EV_Driver.py localhost:9092 driver_001` | 连接到Kafka |

### 端口分配建议

| 服务 | 默认端口 | 说明 |
|------|---------|------|
| Central | 5000 | 可配置 |
| Kafka | 9092 | 标准端口 |
| Engine | 动态 | 自动分配或使用--debug_port指定 |

### 配置文件位置

- `.env`: 项目根目录（可选）
- `ev_central.db`: SQLite数据库文件（自动创建）
- `requirements.txt`: Python依赖列表

---

## 联系支持

如遇到部署问题，请检查:
1. 日志输出中的错误信息
2. 网络连接状态
3. 端口占用情况
4. Kafka运行状态

更多信息请参考:
- `ARCHITECTURE_DIAGRAM.md` - 系统架构说明
- `TESTING_GUIDE.md` - 测试指南
- `TAREAS_PENDIENTES.md` - 任务清单

