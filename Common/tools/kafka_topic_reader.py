"""
Kafka Topic Reader - 读取所有定义的Kafka主题消息
用于调试和监控Kafka中的消息
"""

import json
import logging
import sys
import argparse
from datetime import datetime
from kafka import KafkaConsumer, KafkaAdminClient
from kafka.errors import KafkaError
from dotenv import load_dotenv
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 禁用Kafka库的详细日志
logging.getLogger("kafka").setLevel(logging.WARNING)
logging.getLogger("kafka.client").setLevel(logging.WARNING)
logging.getLogger("kafka.conn").setLevel(logging.WARNING)


class KafkaTopicReader:
    """Kafka主题读取器"""

    def __init__(self, broker_address):
        """
        初始化Kafka主题读取器

        Args:
            broker_address: Kafka broker地址
        """
        self.broker_address = broker_address
        self.admin_client = None

    def connect(self):
        """连接到Kafka"""
        try:
            self.admin_client = KafkaAdminClient(
                bootstrap_servers=[self.broker_address],
                request_timeout_ms=10000
            )
            logger.info(f"Successfully connected to Kafka: {self.broker_address}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False

    def list_topics(self):
        """列出所有主题"""
        try:
            topics = self.admin_client.list_topics()
            logger.info(f"Found {len(topics)} topics")
            return sorted(topics)
        except Exception as e:
            logger.error(f"Failed to get topic list: {e}")
            return []

    def get_topic_metadata(self, topic):
        """获取主题元数据"""
        try:
            metadata = self.admin_client.describe_topics([topic])
            return metadata
        except Exception as e:
            logger.error(f"Failed to get topic {topic} metadata: {e}")
            return None

    def read_topic_messages(self, topic, max_messages=100, from_beginning=True):
        """
        读取主题消息

        Args:
            topic: 主题名称
            max_messages: 最大读取消息数，0表示无限制
            from_beginning: 是否从头开始读取
        """
        try:
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=[self.broker_address],
                value_deserializer=lambda m: json.loads(m.decode('utf-8')) if m else None,
                auto_offset_reset='earliest' if from_beginning else 'latest',
                enable_auto_commit=False,
                consumer_timeout_ms=5000,  # 5秒超时
                group_id=f'topic_reader_{datetime.now().timestamp()}'
            )

            logger.info(f"\n{'='*80}")
            logger.info(f"Topic: {topic}")
            logger.info(f"{'='*80}")

            message_count = 0

            for message in consumer:
                message_count += 1

                print(f"\n--- Message #{message_count} ---")
                print(f"Partition: {message.partition}")
                print(f"Offset: {message.offset}")
                print(f"Timestamp: {datetime.fromtimestamp(message.timestamp/1000).strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"Content: {json.dumps(message.value, ensure_ascii=False, indent=2)}")

                if max_messages > 0 and message_count >= max_messages:
                    logger.info(f"Read {max_messages} messages, stopping")
                    break

            if message_count == 0:
                logger.info(f"Topic {topic} has no messages")
            else:
                logger.info(f"Topic {topic} read {message_count} messages in total")

            consumer.close()

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
        except Exception as e:
            logger.error(f"Failed to read messages from topic {topic}: {e}")

    def close(self):
        """关闭连接"""
        if self.admin_client:
            self.admin_client.close()
            logger.info("Kafka connection closed")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Kafka主题消息读取工具')
    parser.add_argument('-b', '--broker',
                       help='Kafka broker地址 (默认从.env读取)',
                       default=None)
    parser.add_argument('-t', '--topic',
                       help='指定要读取的主题名称 (不指定则列出所有主题)',
                       default=None)
    parser.add_argument('-n', '--num-messages',
                       type=int,
                       help='读取的最大消息数 (默认100, 0表示无限制)',
                       default=100)
    parser.add_argument('-a', '--all',
                       action='store_true',
                       help='读取所有主题的消息')
    parser.add_argument('--latest',
                       action='store_true',
                       help='只读取最新消息 (默认从头开始)')

    args = parser.parse_args()

    # 加载环境变量
    load_dotenv()

    # 获取broker地址
    broker_address = args.broker or os.getenv('BROKER_ADDRESS', 'localhost:9092')

    logger.info(f"Using Kafka Broker: {broker_address}")

    # 创建读取器
    reader = KafkaTopicReader(broker_address)

    if not reader.connect():
        logger.error("Failed to connect to Kafka, exiting")
        sys.exit(1)

    try:
        # 获取所有主题
        topics = reader.list_topics()

        if not topics:
            logger.warning("No topics found")
            return

        # 过滤掉内部主题
        user_topics = [t for t in topics if not t.startswith('__')]

        print(f"\n{'='*80}")
        print(f"Available Topics ({len(user_topics)}):")
        print(f"{'='*80}")
        for i, topic in enumerate(user_topics, 1):
            print(f"{i}. {topic}")
        print(f"{'='*80}\n")

        # 根据参数决定读取哪些主题
        if args.all:
            # 读取所有主题
            for topic in user_topics:
                reader.read_topic_messages(
                    topic,
                    max_messages=args.num_messages,
                    from_beginning=not args.latest
                )
        elif args.topic:
            # 读取指定主题
            if args.topic in topics:
                reader.read_topic_messages(
                    args.topic,
                    max_messages=args.num_messages,
                    from_beginning=not args.latest
                )
            else:
                logger.error(f"Topic '{args.topic}' does not exist")
        else:
            # 交互式选择
            print("Please select a topic to read (enter a number, 'all' to read all, 'q' to quit):")
            choice = input("> ").strip()

            if choice.lower() == 'q':
                return
            elif choice.lower() == 'all':
                for topic in user_topics:
                    reader.read_topic_messages(
                        topic,
                        max_messages=args.num_messages,
                        from_beginning=not args.latest
                    )
            else:
                try:
                    index = int(choice) - 1
                    if 0 <= index < len(user_topics):
                        topic = user_topics[index]
                        reader.read_topic_messages(
                            topic,
                            max_messages=args.num_messages,
                            from_beginning=not args.latest
                        )
                    else:
                        logger.error("Invalid selection")
                except ValueError:
                    logger.error("Please enter a valid number")

    finally:
        reader.close()


if __name__ == "__main__":
    main()
