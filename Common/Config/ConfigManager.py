import os
from dotenv import load_dotenv


class ConfigManager:
    """
    Configuration controller that loads settings from a .env file and environment variables.
    """

    _instance = None
    _config_data = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self, file_path=".env"):
        try:
            load_dotenv(file_path)
            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if "=" in line:
                            key, value = line.split("=", 1)
                            self._config_data[key.strip()] = value.strip()
        except FileNotFoundError:
            print(f"Warning: Config file '{file_path}' not found.")
    @classmethod
    def get(cls, key, default=None):
        """
        get the value of a configuration item by key.
        """

        if key in cls._config_data:
            return cls._config_data[key]

        return os.getenv(key, default)

    @classmethod
    def load_all(cls):
        return cls._config_data.copy()

    def get_debug_mode(self):
        return self.get("DEBUG_MODE", "False").lower() in ("true", "1", "yes")

    
    def get_broker(self):
        ip_port = self.get("BROKER_ADDRESS", "localhost:9092").split(":")
        return (ip_port[0], int(ip_port[1]))

    def get_db(self):
        ip_port = self.get("DB_ADDRESS", "localhost:5432").split(":")
        return (ip_port[0], int(ip_port[1]))

    
    def get_listen_port(self):
        return int(self.get("LISTEN_PORT", "5000"))
    
    def get_db_path(self):
        return self.get("DB_PATH", "ev_central.db")
        
    def get_ip_port_ev_cp_e(self):
        ip_port = self.get("IP_PORT_EV_CP_E", "localhost:6000").split(":")
        return (ip_port[0], int(ip_port[1]))
    def get_ip_port_ev_cp_central(self):
        ip_port = self.get("IP_PORT_EV_CP_CENTRAL", "localhost:5000").split(":")
        return (ip_port[0], int(ip_port[1]))

    def get_ip_port_ev_m(self):
        ip_port = self.get("IP_PORT_EV_M", "localhost:6000").split(":")
        return (ip_port[0], int(ip_port[1]))
    
if __name__ == "__main__":

    config = ConfigManager()

    debug_mode = config.get("DEBUG_MODE") == "True"
    print(f"DEBUG_MODE: {debug_mode}")
    print(type(debug_mode))
    if debug_mode:
        print("Debug mode is enabled.")
        print(config.get_debug_mode())
