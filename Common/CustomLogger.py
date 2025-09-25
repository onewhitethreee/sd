import logging
import colorlog

class CustomLogger:
    @staticmethod
    def get_logger(level=logging.DEBUG):
        logger = logging.getLogger()
        logger.setLevel(level)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        color_formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(levelname)s:%(asctime)s: %(message)s",  # 在这里加入了%(asctime)s
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
            datefmt="%Y-%m-%d %H:%M:%S",  # 可以设置时间的显示格式
        )

        console_handler.setFormatter(color_formatter)
        for handler in logger.handlers:
            logger.removeHandler(handler)
        logger.addHandler(console_handler)
        return logger

if __name__ == "__main__":
    logger = CustomLogger.get_logger(logging.DEBUG)
    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")
    logger.critical("critical message")
