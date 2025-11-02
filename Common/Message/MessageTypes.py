"""
消息类型常量定义

此模块集中管理整个充电系统中使用的所有消息类型常量，避免硬编码字符串。
统一的常量定义有助于：
1. 防止拼写错误
2. 提供IDE自动补全
3. 便于全局搜索和重构
4. 清晰地展示系统中所有的消息类型

使用方法：
    from Common.Message.MessageTypes import MessageTypes, ResponseStatus

    # 创建消息
    message = {
        "type": MessageTypes.CHARGE_REQUEST,
        "message_id": str(uuid.uuid4()),
        ...
    }

    # 检查响应状态
    if response.get("status") == ResponseStatus.SUCCESS:
        ...
"""


class MessageTypes:
    """
    消息类型常量类

    按照组件和功能分组，清晰地展示消息的发送方和接收方。
    """

    # ==================== Engine 相关消息 ====================

    # Engine 接收的消息（来自 Monitor）
    HEALTH_CHECK_REQUEST = "health_check_request"
    START_CHARGING_COMMAND = "start_charging_command"
    STOP_CHARGING_COMMAND = "stop_charging_command"

    # Engine 发送的消息（发送给 Monitor）
    HEALTH_CHECK_RESPONSE = "health_check_response"
    COMMAND_RESPONSE = "command_response"
    ERROR_RESPONSE = "error_response"
    CHARGING_DATA = "charging_data"
    CHARGE_COMPLETION = "charge_completion"

    # ==================== Monitor 相关消息 ====================

    # Monitor 发送到 Central
    REGISTER_REQUEST = "register_request"
    HEARTBEAT_REQUEST = "heartbeat_request"
    AUTH_REQUEST = "auth_request"
    FAULT_NOTIFICATION = "fault_notification"
    STATUS_UPDATE = "status_update"
    RECOVERY_NOTIFICATION = "recovery_notification"

    # Monitor 接收自 Central
    REGISTER_RESPONSE = "register_response"
    HEARTBEAT_RESPONSE = "heartbeat_response"
    STOP_CP_COMMAND = "stop_cp_command"
    RESUME_CP_COMMAND = "resume_cp_command"

    # ==================== Driver 相关消息 ====================

    # Driver 发送到 Central
    CHARGE_REQUEST = "charge_request"
    STOP_CHARGING_REQUEST = "stop_charging_request"
    AVAILABLE_CPS_REQUEST = "available_cps_request"
    CHARGING_HISTORY_REQUEST = "charging_history_request"  # 新增：查询充电历史

    # Driver 接收自 Central
    CHARGE_REQUEST_RESPONSE = "charge_request_response"
    CHARGING_STATUS_UPDATE = "charging_status_update"
    STOP_CHARGING_RESPONSE = "stop_charging_response"
    AVAILABLE_CPS_RESPONSE = "available_cps_response"
    CHARGING_HISTORY_RESPONSE = "charging_history_response"  # 新增：充电历史响应

    # 注意：CHARGING_DATA 和 CHARGE_COMPLETION 在上面 Engine 部分已定义
    # Driver 也会接收这两种消息（通过 Central 转发）

    # ==================== Admin 相关消息 ====================

    MANUAL_COMMAND = "manual_command"

    # ==================== 系统事件消息 ====================

    CONNECTION_LOST = "connection_lost"
    CONNECTION_ERROR = "connection_error"

    # ==================== 旧消息类型（已弃用，保留用于兼容） ====================

    # 以下消息类型已不再使用，但保留常量以便识别和过渡
    # 如果在代码中看到这些类型，应该被移除

    # DEPRECATED: Central 从不发送以下响应消息
    CHARGING_DATA_RESPONSE = "charging_data_response"  # ❌ 已弃用
    FAULT_NOTIFICATION_RESPONSE = "fault_notification_response"  # ❌ 已弃用
    STATUS_UPDATE_RESPONSE = "status_update_response"  # ❌ 已弃用
    CHARGE_COMPLETION_RESPONSE = "charge_completion_response"  # ❌ 已弃用

    # DEPRECATED: Engine 中已删除的命令
    STOP_COMMAND = "stop_command"  # ❌ 已弃用，使用 STOP_CHARGING_COMMAND
    RESUME_COMMAND = "resume_command"  # ❌ 已弃用


class ResponseStatus:
    """
    响应状态常量

    用于统一所有响应消息中的 status 字段值。
    """
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"


class CPStatus:
    """
    充电点状态常量

    定义充电点可能的状态值。
    """
    DISCONNECTED = "DISCONNECTED"  # 未连接
    ACTIVE = "ACTIVE"              # 正常工作
    FAULTY = "FAULTY"              # 故障
    CHARGING = "CHARGING"          # 充电中
    AVAILABLE = "AVAILABLE"        # 可用
    UNAVAILABLE = "UNAVAILABLE"    # 不可用


class MessageFields:
    """
    消息字段名称常量

    定义消息中常用的字段名称，确保一致性。
    """
    # 基础字段
    TYPE = "type"
    MESSAGE_ID = "message_id"
    TIMESTAMP = "timestamp"

    # 标识字段
    CP_ID = "cp_id"
    DRIVER_ID = "driver_id"
    SESSION_ID = "session_id"

    # 状态和结果
    STATUS = "status"
    MESSAGE = "message"
    ERROR = "error"
    REASON = "reason"

    # 充电相关
    ENERGY_CONSUMED_KWH = "energy_consumed_kwh"
    TOTAL_COST = "total_cost"
    CHARGING_RATE = "charging_rate"
    PRICE_PER_KWH = "price_per_kwh"
    MAX_CHARGING_RATE_KW = "max_charging_rate_kw"

    # 其他
    CHARGING_POINTS = "charging_points"
    FAULT_TYPE = "fault_type"
    ENGINE_STATUS = "engine_status"
    IS_CHARGING = "is_charging"
    PROGRESS = "progress"


# ==================== 辅助函数 ====================

def is_deprecated_message_type(msg_type: str) -> bool:
    """
    检查消息类型是否已弃用

    Args:
        msg_type: 消息类型字符串

    Returns:
        bool: 如果消息类型已弃用返回True
    """
    deprecated_types = {
        MessageTypes.CHARGING_DATA_RESPONSE,
        MessageTypes.FAULT_NOTIFICATION_RESPONSE,
        MessageTypes.STATUS_UPDATE_RESPONSE,
        MessageTypes.CHARGE_COMPLETION_RESPONSE,
        MessageTypes.STOP_COMMAND,
        MessageTypes.RESUME_COMMAND,
    }
    return msg_type in deprecated_types


def get_message_category(msg_type: str) -> str:
    """
    获取消息类型的分类

    Args:
        msg_type: 消息类型字符串

    Returns:
        str: 消息分类（"request", "response", "command", "notification", "event"）
    """
    if msg_type.endswith("_request"):
        return "request"
    elif msg_type.endswith("_response"):
        return "response"
    elif msg_type.endswith("_command"):
        return "command"
    elif msg_type in [MessageTypes.CONNECTION_LOST, MessageTypes.CONNECTION_ERROR]:
        return "event"
    else:
        return "notification"


def validate_message_structure(message: dict) -> tuple[bool, str]:
    """
    验证消息的基本结构

    Args:
        message: 消息字典

    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not isinstance(message, dict):
        return False, "Message must be a dictionary"

    if MessageFields.TYPE not in message:
        return False, f"Missing required field: {MessageFields.TYPE}"

    if MessageFields.MESSAGE_ID not in message:
        return False, f"Missing required field: {MessageFields.MESSAGE_ID}"

    msg_type = message.get(MessageFields.TYPE)
    if is_deprecated_message_type(msg_type):
        return False, f"Message type '{msg_type}' is deprecated"

    return True, ""


# ==================== 消息类型集合（用于快速检查） ====================

# 所有有效的消息类型集合
VALID_MESSAGE_TYPES = {
    # Engine
    MessageTypes.HEALTH_CHECK_REQUEST,
    MessageTypes.START_CHARGING_COMMAND,
    MessageTypes.STOP_CHARGING_COMMAND,
    MessageTypes.HEALTH_CHECK_RESPONSE,
    MessageTypes.COMMAND_RESPONSE,
    MessageTypes.ERROR_RESPONSE,
    MessageTypes.CHARGING_DATA,
    MessageTypes.CHARGE_COMPLETION,

    # Monitor
    MessageTypes.REGISTER_REQUEST,
    MessageTypes.HEARTBEAT_REQUEST,
    MessageTypes.AUTH_REQUEST,
    MessageTypes.FAULT_NOTIFICATION,
    MessageTypes.STATUS_UPDATE,
    MessageTypes.RECOVERY_NOTIFICATION,
    MessageTypes.REGISTER_RESPONSE,
    MessageTypes.HEARTBEAT_RESPONSE,
    MessageTypes.STOP_CP_COMMAND,
    MessageTypes.RESUME_CP_COMMAND,

    # Driver
    MessageTypes.CHARGE_REQUEST,
    MessageTypes.STOP_CHARGING_REQUEST,
    MessageTypes.AVAILABLE_CPS_REQUEST,
    MessageTypes.CHARGING_HISTORY_REQUEST,
    MessageTypes.CHARGE_REQUEST_RESPONSE,
    MessageTypes.CHARGING_STATUS_UPDATE,
    MessageTypes.STOP_CHARGING_RESPONSE,
    MessageTypes.AVAILABLE_CPS_RESPONSE,
    MessageTypes.CHARGING_HISTORY_RESPONSE,

    # Admin
    MessageTypes.MANUAL_COMMAND,

    # System
    MessageTypes.CONNECTION_LOST,
    MessageTypes.CONNECTION_ERROR,
}


def is_valid_message_type(msg_type: str) -> bool:
    """
    检查消息类型是否有效

    Args:
        msg_type: 消息类型字符串

    Returns:
        bool: 如果消息类型有效返回True
    """
    return msg_type in VALID_MESSAGE_TYPES
