import argparse
import json

    
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




if __name__ == "__main__":
    tools = AppArgumentParser("MyApp", "This is my application")
    args = tools.parse_args()
    print(f"Parsed arguments: {args}")
    

