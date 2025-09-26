import os
from dotenv import load_dotenv
class ConfigManager:
    def __init__(self):
        self.config = {}

    @staticmethod
    def load_config(file_path):
        load_dotenv(file_path)
        return {key: os.getenv(key) for key in os.environ.keys()}
    @staticmethod
    def get_config(key):
        return ConfigManager.load_config(".env").get(key)

if __name__ == "__main__":
    print(ConfigManager.load_config(".env").get("DEBUG_MODE"))