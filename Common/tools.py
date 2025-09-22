import argparse
import json

class AppArgumentParser:
    """
    Control de los argumentos de la aplicación.
    """
    def __init__(self, app_name, description):
        self.app_name = app_name
        self.parser = argparse.ArgumentParser(prog=app_name, description=description, add_help=True)
        
    def add_argument(self, *args, **kwargs):
        self.parser.add_argument(*args, **kwargs)
    def parse_args(self):
        return self.parser.parse_args()

    
def ip_port_type(value):
    try:
        ip, port = value.split(":")
        if not (ip and port.isdigit() and 1024 <= int(port) < 65536):
            raise ValueError("Invalid IP or port")
        if not ip:
            raise ValueError("IP cannot be empty")
        return ip, int(port)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid IP:Port format: {value}. Expected 'IP:PORT'. {e}")


class MessageFormatter:
    """
    Mensajería basada en el estándar de empaquetado <STX><DATA><ETX><LRC>
    donde:
        STX: Start of Text (0x02)
        DATA: Mensaje en formato JSON
        ETX: End of Text (0x03)
        LRC: Longitud de Redundancia Cíclica (XOR de todos los bytes en DATA)
    """
    STX = b'\x02' # Start of Text(ASCII)
    ETX = b'\x03' # End of Text(ASCII)

    def __init__(self, encoding='utf-8'):
        self.encoding = encoding

    def calculate_lrc(self, data):
        lrc = 0
        for byte in data:
            lrc ^= byte
        return bytes([lrc])
    
    def pack_message(self, message):        
        if not isinstance(message, dict):
            raise TypeError("El mensaje debe ser un diccionario.")
        try:
            message_json = json.dumps(message).encode(self.encoding)
        except (TypeError, ValueError) as e:
            raise ValueError("El mensaje no es serializable a JSON.") from e
        lrc = self.calculate_lrc(message_json)
        return self.STX + message_json + self.ETX + lrc
    
    
    def unpack_message(self, message_str):
        if not (message_str.startswith(self.STX) and self.ETX in message_str):
            raise ValueError("Mensaje mal formado: falta STX o ETX.")
        try:
            etx_index = message_str.index(self.ETX)
            message_json = message_str[1:etx_index]
            lrc_received = message_str[etx_index + 1:etx_index + 2]
            lrc_calculated = self.calculate_lrc(message_json)
            
            if lrc_received != lrc_calculated:
                raise ValueError("LRC no coincide, mensaje corrupto.")
            message = json.loads(message_json.decode(self.encoding))
            return message
        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError("Error al desempaquetar el mensaje.") from e

if __name__ == "__main__":
    # tools = AppArgumentParser("MyApp", "This is my application")
    # args = tools.parse_args()
    # print(f"Parsed arguments: {args}")
    formatter = MessageFormatter()
    original_message = {"type": "greeting", "content": "Hello, World!"}
    packed = formatter.pack_message(original_message)
    print(f"Packed message: {packed}")
    unpacked = formatter.unpack_message(packed)
    print(f"Unpacked message: {unpacked}")

