import json


class MessageFormatter:
    """
    Mensajería basada en el estándar de empaquetado <STX><DATA><ETX><LRC>
    donde:
        STX: Start of Text (0x02)
        DATA: Mensaje en formato JSON
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
    def pack_message(message, encoding="utf-8"):
        """
        Packs a message dictionary into the specified byte string format.
        """
        if not isinstance(message, dict):
            raise TypeError("El mensaje debe ser un diccionario.")
        try:
            message_json = json.dumps(message).encode(encoding)
        except (TypeError, ValueError) as e:
            raise ValueError("El mensaje no es serializable a JSON.") from e
        lrc = MessageFormatter._calculate_lrc(message_json)
        return MessageFormatter.STX + message_json + MessageFormatter.ETX + lrc

    @staticmethod
    def unpack_message(message_str, encoding="utf-8"):
        """
        Unpacks a message from the given byte string.
        """
        if not (
            message_str.startswith(MessageFormatter.STX)
            and MessageFormatter.ETX in message_str
        ):
            raise ValueError("Mensaje mal formado: falta STX o ETX.")
        try:
            etx_index = message_str.index(MessageFormatter.ETX)
            message_json = message_str[1:etx_index]
            lrc_received = message_str[etx_index + 1 : etx_index + 2]
            lrc_calculated = MessageFormatter._calculate_lrc(message_json)

            if lrc_received != lrc_calculated:
                raise ValueError("LRC no coincide, mensaje corrupto.")
            message = json.loads(message_json.decode(encoding))
            return message
        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError("Error al desempaquetar el mensaje.") from e

    @staticmethod
    def extract_complete_message(buffer):
        """
        Extract a complete message from the buffer.
        Returns a tuple (remaining_buffer, message) where:
            - remaining_buffer is the buffer after extracting the message
            - message is the extracted message dictionary or None if no complete message is found
        """
        if MessageFormatter.STX not in buffer:
            return buffer, None

        stx_index = buffer.index(MessageFormatter.STX)

        # find where ETX is
        try:
            etx_index = buffer.index(MessageFormatter.ETX, stx_index)
        except ValueError:
            # ETX not found, message is incomplete
            return buffer, None

        # Check for LRC
        if len(buffer) < etx_index + 2:
            # Not enough data to contain LRC
            return buffer, None

        # Extract complete message
        message_bytes = buffer[stx_index : etx_index + 2]

        try:
            message = MessageFormatter.unpack_message(message_bytes)
            # Remove the processed message from the buffer
            remaining_buffer = buffer[etx_index + 2 :]
            return remaining_buffer, message
        except ValueError:
            # Message format error, skip this STX
            return buffer[stx_index + 1 :], None
    @staticmethod
    def create_response_message(cp_type, message_id, status, info=""):
        """
        a response message template
        """
        return {
            "type": cp_type,
            "message_id": message_id,
            "status": status,
            "info": info,
        }

if __name__ == "__main__":

    original_message = {"type": "greeting", "content": "Hello, World!"}
    packed = MessageFormatter.pack_message(original_message)
    print(f"Packed message: {packed}")
    unpacked = MessageFormatter.unpack_message(packed)
    print(f"Unpacked message: {unpacked}")
