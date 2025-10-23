"""
消息转换器 - 统一处理消息格式转换
负责在字典格式和字符串列表格式之间进行双向转换
"""


class MessageTransformer:
    """
    统一的消息转换工具类
    负责在字典格式和字符串列表格式之间进行双向转换
    
    消息格式说明：
    - 字典格式：应用层使用，易于理解和维护
      {"type": "register_request", "message_id": "123", "id": "CP001", ...}
    
    - 列表格式：网络传输使用，轻量级
      ["register_request", "123", "CP001", ...]
    
    - 二进制格式：实际网络传输，包含STX/ETX/LRC
      b'\x02register_request#123#CP001#...\x03\xXX'
    """

    # 定义所有消息类型的字段顺序
    # 这是消息格式的核心定义，所有转换都基于这个映射
    MESSAGE_FIELD_MAPPING = {
        # 注册相关
        "register_request": ["type", "message_id", "id", "location", "price_per_kwh"],
        "register_response": ["type", "message_id", "status", "info"],

        # 心跳相关
        "heartbeat_request": ["type", "message_id", "id"],
        "heartbeat_response": ["type", "message_id", "status", "info"],

        # 充电请求相关
        "charge_request": ["type", "message_id", "driver_id", "cp_id"],
        "charge_request_response": [
            "type",
            "message_id",
            "status",
            "info",
            "session_id",
        ],

        # 充电数据相关
        "charging_data": [
            "type",
            "message_id",
            "cp_id",
            "session_id",
            "energy_consumed",
            "total_cost",
            "charging_rate",
        ],
        "charging_data_response": ["type", "message_id", "status", "info"],

        # 充电完成相关
        "charge_completion": [
            "type",
            "message_id",
            "cp_id",
            "session_id",
            "energy_consumed",
            "total_cost",
        ],
        "charge_completion_response": ["type", "message_id", "status", "info"],

        # 故障通知相关
        "fault_notification": ["type", "message_id", "cp_id", "fault_code", "fault_description"],
        "fault_notification_response": ["type", "message_id", "status", "info"],

        # 状态更新相关
        "status_update": ["type", "message_id", "cp_id", "new_status"],
        "status_update_response": ["type", "message_id", "status", "info"],

        # 可用充电点相关
        "available_cps_request": ["type", "message_id", "driver_id"],
        "available_cps_response": ["type", "message_id", "status", "info"],

        # 恢复通知相关
        "recovery_notification": ["type", "message_id", "cp_id"],
        "recovery_notification_response": ["type", "message_id", "status", "info"],

        # 启动充电命令相关
        "start_charging_command": [
            "type",
            "message_id",
            "cp_id",
            "session_id",
            "driver_id",
        ],
        "start_charging_response": ["type", "message_id", "status", "info"],

        # 健康检查相关
        "health_check_request": ["type", "message_id", "id"],
        "health_check_response": [
            "type",
            "message_id",
            "status",
            "engine_status",
            "timestamp",
            "is_charging",
        ],

        # 命令相关
        "command_response": ["type", "message_id", "status", "message"],
        "stop_command": ["type", "message_id", "id"],

        # 错误相关
        "error_response": ["type", "message_id", "status", "info"],
    }

    @staticmethod
    def to_list(message):
        """
        将消息转换为字符串列表格式（字典 → 列表）
        
        Args:
            message: 字典格式的消息或已经是列表格式
            
        Returns:
            字符串列表格式的消息
        """
        if isinstance(message, list):
            return message

        if isinstance(message, dict):
            message_type = message.get("type", "")
            field_names = MessageTransformer.MESSAGE_FIELD_MAPPING.get(
                message_type, list(message.keys())
            )

            result = []
            for field in field_names:
                value = message.get(field, "")
                result.append(str(value) if value is not None else "")

            return result

        return [str(message)]

    @staticmethod
    def to_dict(message):
        """
        将消息转换为字典格式（列表 → 字典）
        
        Args:
            message: 字符串列表格式的消息或已经是字典格式
            
        Returns:
            字典格式的消息
        """
        if isinstance(message, dict):
            return message

        if isinstance(message, list) and len(message) > 0:
            message_type = message[0]
            field_names = MessageTransformer.MESSAGE_FIELD_MAPPING.get(
                message_type,
                [f"field_{i}" for i in range(len(message))]
            )

            message_dict = {}
            for i, field_value in enumerate(message):
                if i < len(field_names):
                    field_name = field_names[i]
                    message_dict[field_name] = field_value
                else:
                    message_dict[f"extra_field_{i}"] = field_value

            return message_dict

        return {}

    @staticmethod
    def to_dict_with_defaults(message):
        """
        将消息转换为字典格式，并填充默认值
        
        Args:
            message: 字符串列表格式的消息
            
        Returns:
            字典格式的消息（包含默认值）
        """
        message_dict = MessageTransformer.to_dict(message)
        
        # 确保有type字段
        if "type" not in message_dict and len(message) > 0:
            message_dict["type"] = message[0]
        
        # 确保有message_id字段
        if "message_id" not in message_dict:
            message_dict["message_id"] = ""
        
        return message_dict

    @staticmethod
    def add_message_type(message_type, field_names):
        """
        添加自定义消息类型的字段映射
        
        Args:
            message_type: 消息类型
            field_names: 字段名称列表
        """
        MessageTransformer.MESSAGE_FIELD_MAPPING[message_type] = field_names

    @staticmethod
    def get_field_names(message_type):
        """
        获取指定消息类型的字段名称
        
        Args:
            message_type: 消息类型
            
        Returns:
            字段名称列表
        """
        return MessageTransformer.MESSAGE_FIELD_MAPPING.get(message_type, [])

    @staticmethod
    def get_field(message_dict, field_name, default=None):
        """
        安全地获取消息字段值
        
        Args:
            message_dict: 消息字典
            field_name: 字段名称
            default: 默认值
            
        Returns:
            字段值或默认值
        """
        return message_dict.get(field_name, default)

