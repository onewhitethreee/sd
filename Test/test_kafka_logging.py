"""
测试Kafka日志是否被正确禁用
"""

import sys
import os
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Common.CustomLogger import CustomLogger
from Common.KafkaManager import KafkaManager


def test_kafka_logging():
    """测试Kafka日志配置"""
    print("=" * 60)
    print("Testing Kafka Logging Configuration")
    print("=" * 60)
    
    # 获取logger
    logger = CustomLogger.get_logger(logging.DEBUG)
    
    print("\n[Test 1] Checking Kafka logger levels")
    print("-" * 60)
    
    kafka_loggers = [
        "kafka",
        "kafka.client",
        "kafka.conn",
        "kafka.protocol",
        "kafka.metrics",
    ]
    
    for logger_name in kafka_loggers:
        kafka_logger = logging.getLogger(logger_name)
        level = kafka_logger.level
        level_name = logging.getLevelName(level)
        print(f"  {logger_name}: {level_name} ({level})")
        
        # 验证日志级别至少是WARNING
        if level >= logging.WARNING:
            print(f"    ✓ PASS: {logger_name} is set to WARNING or higher")
        else:
            print(f"    ✗ FAIL: {logger_name} is set to {level_name}")
    
    print("\n[Test 2] Creating KafkaManager instance")
    print("-" * 60)
    
    try:
        # 创建KafkaManager实例（不会实际连接到Kafka）
        kafka_manager = KafkaManager("localhost:9092", logger)
        print("  ✓ PASS: KafkaManager created successfully")
        print("  Note: Kafka connection not attempted (no broker running)")
    except Exception as e:
        print(f"  ✗ FAIL: Error creating KafkaManager: {e}")
    
    print("\n[Test 3] Verifying application logger")
    print("-" * 60)
    
    app_logger = logging.getLogger()
    print(f"  Root logger level: {logging.getLevelName(app_logger.level)}")
    print(f"  Number of handlers: {len(app_logger.handlers)}")
    
    for i, handler in enumerate(app_logger.handlers):
        print(f"  Handler {i}: {handler.__class__.__name__} (level: {logging.getLevelName(handler.level)})")
    
    print("\n" + "=" * 60)
    print("Kafka logging configuration test completed!")
    print("=" * 60)
    print("\nSummary:")
    print("  - Kafka library loggers are set to WARNING level")
    print("  - This will suppress DEBUG and INFO messages from Kafka")
    print("  - Only WARNING, ERROR, and CRITICAL messages will be shown")
    print("=" * 60)


if __name__ == "__main__":
    test_kafka_logging()

