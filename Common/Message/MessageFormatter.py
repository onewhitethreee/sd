

class MessageFormatter:
    """
    Mensajería basada en el estándar de empaquetado <STX><DATA><ETX><LRC>
    donde:
        STX: Start of Text (0x02)
        DATA: Mensaje字段，用'#'分隔，例如 "Código Operación#campo1#...#campo n"
        ETX: End of Text (0x03)
        LRC: Longitud de Redundancia Cíclica (XOR de todos los bytes en DATA)
    """

    STX = b"\x02"  # Start of Text(ASCII)
    ETX = b"\x03"  # End of Text(ASCII)

    def __init__(self, encoding="utf-8"):
        self.encoding = encoding

    @staticmethod
    def _calculate_lrc(data):
        lrc = 0
        for byte in data:
            lrc ^= byte
        return bytes([lrc])

    @staticmethod
    def pack_message(message_fields_list, encoding="utf-8"):
        """
        Packs a list of message fields into the specified byte string format.
        message_fields_list: A list of strings, e.g., ["OPERATION_CODE", "field1", "field2"]
        """
        if not isinstance(message_fields_list, (list, tuple)):
            raise TypeError("消息必须是一个字符串列表或元组。")
        if not all(isinstance(field, str) for field in message_fields_list):
            raise TypeError("消息中的所有字段都必须是字符串。")

        try:
            message_data_str = "#".join(message_fields_list)
            message_data_bytes = message_data_str.encode(encoding)
        except Exception as e:
            raise ValueError(f"No pude codificar el mensaje: {e}") from e

        lrc = MessageFormatter._calculate_lrc(message_data_bytes)
        return MessageFormatter.STX + message_data_bytes + MessageFormatter.ETX + lrc

    @staticmethod
    def unpack_message(message_str, encoding="utf-8"):
        """
        Unpacks a message from the given byte string.
        Returns a list of strings (message fields).
        """
        if not (
            message_str.startswith(MessageFormatter.STX)
            and MessageFormatter.ETX in message_str
        ):
            raise ValueError("消息格式错误：缺少 STX 或 ETX。")
        try:
            etx_index = message_str.index(MessageFormatter.ETX)
            message_data_bytes = message_str[1:etx_index]  # 现在这是 DATA 部分的 bytes
            lrc_received = message_str[etx_index + 1 : etx_index + 2]
            lrc_calculated = MessageFormatter._calculate_lrc(message_data_bytes)

            if lrc_received != lrc_calculated:
                raise ValueError("LRC 不匹配，消息已损坏。")

            # 就是这样！解码，然后用 # 分割！
            message_data_str = message_data_bytes.decode(encoding)
            message_fields_list = message_data_str.split("#")
            return message_fields_list  # 返回字符串列表
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError(f"解包消息时出错: {e}") from e

    @staticmethod
    def extract_complete_message(buffer):
        """
        Extract a complete message from the buffer.
        Returns a tuple (remaining_buffer, message) where:
            - remaining_buffer is the buffer after extracting the message
            - message is the extracted message (list of strings) or None if no complete message is found
        """
        if MessageFormatter.STX not in buffer:
            return buffer, None

        stx_index = buffer.index(MessageFormatter.STX)

        try:
            etx_index = buffer.index(MessageFormatter.ETX, stx_index)
        except ValueError:
            # ETX not found, message is incomplete
            return buffer, None

        
        if len(buffer) < etx_index + 2:  # +1 for ETX, +1 for LRC
            # Not enough data to contain LRC
            return buffer, None

        message_bytes = buffer[
            stx_index : etx_index + 2
        ]  # stx_index to (etx_index + 1) inclusive for LRC

        try:
            message_fields_list = MessageFormatter.unpack_message(
                message_bytes
            )  
            remaining_buffer = buffer[etx_index + 2 :]
            return remaining_buffer, message_fields_list
        except ValueError:
            
            return buffer[stx_index + 1 :], None

    @staticmethod
    def create_response_message(cp_type, message_id, status, info=""):
        """
        A response message template, now returns a list of strings NOT a dict.
        """
        return [
            cp_type if cp_type else "",
            str(message_id) if message_id is not None else "",  # 确保ID是字符串
            status if status else "",
            info if info else "",
        ]
