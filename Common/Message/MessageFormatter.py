import json


class MessageFormatter:
    
    STX = b"\x02"  # Start of Text (ASCII)
    ETX = b"\x03"  # End of Text (ASCII)

    def __init__(self, encoding="utf-8"):
        self.encoding = encoding

    @staticmethod
    def _calculate_lrc(data):
        """Calular el LRC de los datos."""
        lrc = 0
        for byte in data:
            lrc ^= byte
        return bytes([lrc])

    @staticmethod
    def pack_message(message_dict, encoding="utf-8"):
        """
        
        """
        if not isinstance(message_dict, dict):
            raise TypeError("消息必须是字典格式")

        try:
            message_json = json.dumps(message_dict, ensure_ascii=False)
            message_bytes = message_json.encode(encoding)
        except Exception as e:
            raise ValueError(f"无法编码消息: {e}") from e

        lrc = MessageFormatter._calculate_lrc(message_bytes)
        return MessageFormatter.STX + message_bytes + MessageFormatter.ETX + lrc

    @staticmethod
    def unpack_message(message_bytes, encoding="utf-8"):
        """
        从字节字符串中解包JSON消息。

        Args:
            message_bytes: 打包的字节字符串
            encoding: 编码方式

        Returns:
            消息字典
        """
        if not (
            message_bytes.startswith(MessageFormatter.STX)
            and MessageFormatter.ETX in message_bytes
        ):
            raise ValueError("消息格式不正确")

        try:
            etx_index = message_bytes.index(MessageFormatter.ETX)
            json_bytes = message_bytes[1:etx_index]
            lrc_received = message_bytes[etx_index + 1 : etx_index + 2]
            lrc_calculated = MessageFormatter._calculate_lrc(json_bytes)

            if lrc_received != lrc_calculated:
                raise ValueError("LRC校验失败，消息已损坏")

            message_json = json_bytes.decode(encoding)
            message_dict = json.loads(message_json)
            return message_dict
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"解包消息失败: {e}") from e

    @staticmethod
    def extract_complete_message(buffer):
        """
        从缓冲区中提取完整的消息。

        Args:
            buffer: 字节缓冲区

        Returns:
            (remaining_buffer, message_dict) 元组
            - remaining_buffer: 提取消息后的剩余缓冲区
            - message_dict: 提取的消息字典，如果没有完整消息则为None
        """
        if MessageFormatter.STX not in buffer:
            return buffer, None

        stx_index = buffer.index(MessageFormatter.STX)

        try:
            etx_index = buffer.index(MessageFormatter.ETX, stx_index)
        except ValueError:
            # ETX未找到，消息不完整
            return buffer, None

        # 检查是否有足够的数据包含LRC
        if len(buffer) < etx_index + 2:  # +1 for ETX, +1 for LRC
            return buffer, None

        message_bytes = buffer[stx_index : etx_index + 2]

        try:
            message_dict = MessageFormatter.unpack_message(message_bytes)
            remaining_buffer = buffer[etx_index + 2 :]
            return remaining_buffer, message_dict
        except ValueError:
            # 消息格式错误，跳过这个STX
            return buffer[stx_index + 1 :], None

    @staticmethod
    def create_response_message(cp_type, message_id, status, info="", session_id=None):
        """
        创建响应消息字典。

        Args:
            cp_type: 消息类型
            message_id: 消息ID
            status: 状态 (success/failure)
            info: 信息

        Returns:
            响应消息字典
        """
        return {
            "type": cp_type if cp_type else "",
            "message_id": str(message_id) if message_id is not None else "",
            "status": status if status else "",
            "info": info if info else "",
            "session_id": session_id if session_id else "",
        }
