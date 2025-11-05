import json


class MessageFormatter:
    
    STX = b"\x02"  # Start of Text (ASCII)
    ETX = b"\x03"  # End of Text (ASCII)

    def __init__(self, encoding="utf-8"):
        """
        Inicializar el formateador de mensajes"""
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
        Empaqueta un diccionario de mensaje en un formato de bytes.
        """
        if not isinstance(message_dict, dict):
            raise TypeError("message_dict debe ser un diccionario")

        try:
            message_json = json.dumps(message_dict, ensure_ascii=False)
            message_bytes = message_json.encode(encoding)
        except Exception as e:
            raise ValueError(f"Error al empaquetar mensaje: {e}") from e

        lrc = MessageFormatter._calculate_lrc(message_bytes)
        return MessageFormatter.STX + message_bytes + MessageFormatter.ETX + lrc

    @staticmethod
    def unpack_message(message_bytes, encoding="utf-8"):
        """
        Desempaqueta un mensaje JSON de un string de bytes.

        Args:
            message_bytes: El string de bytes empaquetado
            encoding: El método de codificación

        Returns:
            El diccionario del mensaje
        """
        if not (
            message_bytes.startswith(MessageFormatter.STX)
            and MessageFormatter.ETX in message_bytes
        ):
            raise ValueError("El formato del mensaje no es correcto")

        try:
            etx_index = message_bytes.index(MessageFormatter.ETX)
            json_bytes = message_bytes[1:etx_index]
            lrc_received = message_bytes[etx_index + 1 : etx_index + 2]
            lrc_calculated = MessageFormatter._calculate_lrc(json_bytes)

            if lrc_received != lrc_calculated:
                raise ValueError("LRC no coincide, mensaje corrupto")

            message_json = json_bytes.decode(encoding)
            message_dict = json.loads(message_json)
            return message_dict
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"Error al desempaquetar mensaje: {e}") from e

    @staticmethod
    def extract_complete_message(buffer):
        """
        Extrae un mensaje completo del buffer de bytes.

        Args:
            buffer: El buffer de bytes

        Returns:
            (remaining_buffer, message_dict) tupla donde:
            - remaining_buffer: El buffer restante después de extraer el mensaje
            - message_dict: El mensaje extraído como diccionario, o None si no hay mensaje completo
        """
        if MessageFormatter.STX not in buffer:
            return buffer, None

        stx_index = buffer.index(MessageFormatter.STX)

        try:
            etx_index = buffer.index(MessageFormatter.ETX, stx_index)
        except ValueError:
            # no encontrado ETX, mensaje incompleto
            return buffer, None

        # Comprobar si hay suficientes datos para incluir LRC
        if len(buffer) < etx_index + 2:  # +1 for ETX, +1 for LRC
            return buffer, None

        message_bytes = buffer[stx_index : etx_index + 2]

        try:
            message_dict = MessageFormatter.unpack_message(message_bytes)
            remaining_buffer = buffer[etx_index + 2 :]
            return remaining_buffer, message_dict
        except ValueError:
            # Error al desempaquetar mensaje, saltar este STX
            return buffer[stx_index + 1 :], None

    @staticmethod
    def create_response_message(cp_type, message_id, status, info="", session_id=None):
        """
        Crear un diccionario de mensaje de respuesta.

        Args:
            cp_type: Tipo de mensaje
            message_id: ID del mensaje
            status: Estado (success/failure)
            info: Información

        Returns:
            Diccionario del mensaje de respuesta
        """
        return {
            "type": cp_type if cp_type else "",
            "message_id": str(message_id) if message_id is not None else "",
            "status": status if status else "",
            "info": info if info else "",
            "session_id": session_id if session_id else "",
        }
