"""
Kafka消息队列管理器
用于处理与Kafka的连接、生产者和消费者的创建和管理
"""

import json
import threading
import logging
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

# 禁用Kafka库的详细日志
logging.getLogger("kafka").setLevel(logging.WARNING)
logging.getLogger("kafka.client").setLevel(logging.WARNING)
logging.getLogger("kafka.conn").setLevel(logging.WARNING)
logging.getLogger("kafka.protocol").setLevel(logging.WARNING)
logging.getLogger("kafka.metrics").setLevel(logging.WARNING)


class KafkaManager:
    """
    Kafka管理器类，负责管理Kafka生产者和消费者
    """

    def __init__(self, broker_address, logger=None):
        """
        初始化Kafka管理器

        Args:
            broker_address: Kafka代理地址，格式为 "host:port"
            logger: 日志记录器
        """
        self.broker_address = broker_address
        self.logger = logger or logging.getLogger(__name__)
        self.producer = None
        self.consumers = {}  # {topic: consumer}
        self.consumer_threads = {}  # {topic: thread}
        self.running = False

    def init_producer(self):
        """
        初始化Kafka生产者
        """
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=[self.broker_address],
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
                max_in_flight_requests_per_connection=1,
            )
            self.logger.info(f"Kafka生产者初始化成功: {self.broker_address}")
            return True
        except Exception as e:
            self.logger.error(f"Kafka生产者初始化失败: {e}")
            return False

    def send_message(self, topic, message):
        """
        发送消息到Kafka主题

        Args:
            topic: 主题名称
            message: 消息内容（字典）

        Returns:
            True if successful, False otherwise
        """
        if not self.producer:
            self.logger.error("Kafka生产者未初始化")
            return False

        try:
            future = self.producer.send(topic, value=message)
            record_metadata = future.get(timeout=10)
            self.logger.debug(
                f"消息已发送到主题 {topic}, 分区 {record_metadata.partition}, 偏移量 {record_metadata.offset}"
            )
            return True
        except KafkaError as e:
            self.logger.error(f"发送消息到Kafka失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"发送消息时出错: {e}")
            return False

    def init_consumer(self, topic, group_id, message_callback):
        """
        初始化Kafka消费者

        Args:
            topic: 主题名称
            group_id: 消费者组ID
            message_callback: 消息回调函数

        Returns:
            True if successful, False otherwise
        """
        try:
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=[self.broker_address],
                group_id=group_id,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                max_poll_records=100,
            )

            self.consumers[topic] = consumer

            # 启动消费者线程
            consumer_thread = threading.Thread(
                target=self._consume_messages,
                args=(topic, message_callback),
                daemon=True,
                name=f"KafkaConsumer-{topic}",
            )
            consumer_thread.start()
            self.consumer_threads[topic] = consumer_thread

            self.logger.info(f"Kafka消费者初始化成功: 主题={topic}, 组ID={group_id}")
            return True

        except Exception as e:
            self.logger.error(f"Kafka消费者初始化失败: {e}")
            return False

    def _consume_messages(self, topic, message_callback):
        """
        消费消息的内部方法

        Args:
            topic: 主题名称
            message_callback: 消息回调函数
        """
        consumer = self.consumers.get(topic)
        if not consumer:
            self.logger.error(f"消费者未找到: {topic}")
            return

        self.logger.info(f"开始消费主题 {topic} 的消息")

        try:
            for message in consumer:
                if not self.running:
                    break

                try:
                    self.logger.debug(f"收到消息: {message.value}")
                    message_callback(message.value)
                except Exception as e:
                    self.logger.error(f"处理消息时出错: {e}")

        except Exception as e:
            self.logger.error(f"消费消息时出错: {e}")
        finally:
            self.logger.info(f"停止消费主题 {topic} 的消息")

    def start(self):
        """
        启动Kafka管理器
        """
        self.running = True
        self.logger.info("Kafka管理器已启动")

    def stop(self):
        """
        停止Kafka管理器
        """
        self.running = False

        # 关闭所有消费者
        for topic, consumer in self.consumers.items():
            try:
                consumer.close()
                self.logger.info(f"消费者已关闭: {topic}")
            except Exception as e:
                self.logger.error(f"关闭消费者失败: {e}")

        # 关闭生产者
        if self.producer:
            try:
                self.producer.close()
                self.logger.info("生产者已关闭")
            except Exception as e:
                self.logger.error(f"关闭生产者失败: {e}")

        self.logger.info("Kafka管理器已停止")

    def is_connected(self):
        """
        检查Kafka连接状态
        """
        return self.producer is not None and self.running


# Kafka主题定义
class KafkaTopics:
    """Kafka主题常量定义"""

    # 充电点相关主题
    CHARGING_POINT_REGISTER = "charging_point_register"
    CHARGING_POINT_HEARTBEAT = "charging_point_heartbeat"
    CHARGING_POINT_STATUS = "charging_point_status"
    CHARGING_POINT_FAULT = "charging_point_fault"

    # 充电会话相关主题
    CHARGING_SESSION_START = "charging_session_start"
    CHARGING_SESSION_DATA = "charging_session_data"
    CHARGING_SESSION_COMPLETE = "charging_session_complete"

    # 司机相关主题
    DRIVER_CHARGING_STATUS = "driver_charging_status"
    DRIVER_CHARGING_COMPLETE = "driver_charging_complete"

    # 系统主题
    SYSTEM_EVENTS = "system_events"
    SYSTEM_ALERTS = "system_alerts"
