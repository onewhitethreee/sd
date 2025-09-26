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
        if os.path.exists(file_path):
            load_dotenv(file_path)

            try:
                with open(file_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            if "=" in line:
                                key, value = line.split("=", 1)
                                self._config_data[key.strip()] = value.strip()
            except FileNotFoundError:
                print(f"Warning: Config file '{file_path}' not found.")
        else:
            print(f"Warning: Config file '{file_path}' not found.")

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


if __name__ == "__main__":

    config = ConfigManager()

    debug_mode = config.get("DEBUG_MODE")
    print(f"DEBUG_MODE: {debug_mode}")
    print(type(debug_mode))
    if debug_mode == True:
        print("Debug mode is enabled.")
