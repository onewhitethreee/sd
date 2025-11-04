

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
    Clase para gestionar la conexión y comunicación con kafka. Pruducer and consumer. 
    """

    def __init__(self, broker_address, logger=None):
        """
        inicializar el gestor de Kafka

        Args:
            broker_address: Dirección del broker de Kafka, en formato "host:port"
            logger: Logger personalizado
        """
        self.broker_address = broker_address
        self.logger = logger or logging.getLogger(__name__)
        self.producer = None
        self.consumers = {}  # {topic: consumer}
        self.consumer_threads = {}  # {topic: thread}
        self.running = False

    def init_producer(self):
        """
        Inicializar producer de Kafka
        """
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=[self.broker_address],
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
                max_in_flight_requests_per_connection=1,
            )
            self.logger.info(f"Kafka producer initialized successfully: {self.broker_address}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Kafka producer: {e}")
            return False


    def produce_message(self, topic, message, retry=3):
        """
        Enviar mensaje a un tema de Kafka (versión mejorada, con soporte de reintentos)

        Args:
            topic: Nombre del tema
            message: Contenido del mensaje (diccionario)
            retry: Número de reintentos, por defecto 3

        Returns:
            bool: Si fue exitoso
        """
        if not self.producer:
            self.logger.error("Kafka producer not initialized")
            return False

        import time
        for attempt in range(retry):
            try:
                future = self.producer.send(topic, value=message)
                record_metadata = future.get(timeout=10)
                self.logger.debug(
                    f"Message sent to topic {topic}, partition {record_metadata.partition}, offset {record_metadata.offset}"
                )
                return True
            except KafkaError as e:
                self.logger.warning(f"Failed to send message (attempt {attempt + 1}/{retry}): {e}")
                if attempt == retry - 1:
                    self.logger.error(f"Failed to send message to Kafka after {retry} attempts")
                    return False
                time.sleep(1 * (attempt + 1))  # Exponential backoff
            except Exception as e:
                self.logger.error(f"Error sending message: {e}")
                return False
        return False

    def init_consumer(self, topic, group_id, message_callback):
        """
        Inicializar consumidor de Kafka

        Args:
            topic: Nombre del tema
            group_id: ID del grupo de consumidores
            message_callback: Función de callback para procesar mensajes

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

            consumer_thread = threading.Thread(
                target=self._consume_messages,
                args=(topic, message_callback),
                daemon=True,
                name=f"KafkaConsumer-{topic}",
            )
            consumer_thread.start()
            self.consumer_threads[topic] = consumer_thread

            self.logger.debug(f"Kafka consumer initialized successfully: Topic={topic}, Group ID={group_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize Kafka consumer: {e}")
            return False

    def _consume_messages(self, topic, message_callback):
        """
        Método interno para consumir mensajes

        Args:
            topic: Nombre del tema
            message_callback: Función de callback para procesar mensajes
        """
        consumer = self.consumers.get(topic)
        if not consumer:
            self.logger.error(f"Consumer not found: {topic}")
            return

        self.logger.info(f"Starting to consume messages from topic {topic}")

        try:
            for message in consumer:
                if not self.running:
                    break

                try:
                    self.logger.debug(f"Received message: {message.value}")
                    message_callback(message.value)
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")

        except Exception as e:
            self.logger.error(f"Error consuming messages: {e}")


    def start(self):
        """
        Start the Kafka manager
        """
        self.running = True
        self.logger.info("Kafka manager started")

    def stop(self):
        """
        Stop the Kafka manager
        """
        self.running = False

        # Close all consumers
        for topic, consumer in self.consumers.items():
            try:
                consumer.close()
                self.logger.info(f"Consumer closed: {topic}")
            except Exception as e:
                self.logger.error(f"Failed to close consumer: {e}")

        # Close producer
        if self.producer:
            try:
                self.producer.close()
                self.logger.info("Producer closed successfully")
            except Exception as e:
                self.logger.error(f"Failed to close producer: {e}")

        self.logger.info("Kafka manager stopped")

    def is_connected(self):
        """
        Check Kafka connection status
        """
        return self.producer is not None and self.running

    def subscribe_topic(self, topic, callback, group_id=None):
        """
        Subscribe to a Kafka topic 

        Args:
            topic: Topic name
            callback: Message callback function
            group_id: Consumer group ID, defaults to f"{topic}_group"

        Returns:
            True if successful, False otherwise
        """
        if group_id is None:
            group_id = f"{topic}_group"

        return self.init_consumer(topic, group_id, callback)

    def create_topic_if_not_exists(self, topic, num_partitions=3, replication_factor=1):
        """
        Create a Kafka topic if it does not exist

        Args:
            topic: Topic name
            num_partitions: Number of partitions, defaults to 3
            replication_factor: Replication factor, defaults to 1

        Returns:
            True if successful or already exists, False otherwise
        """
        try:
            from kafka.admin import KafkaAdminClient, NewTopic

            admin = KafkaAdminClient(
                bootstrap_servers=[self.broker_address],
                request_timeout_ms=10000
            )

            existing_topics = admin.list_topics()
            if topic in existing_topics:
                # self.logger.debug(f"Topic {topic} already exists")
                admin.close()
                return True

            new_topic = NewTopic(
                name=topic,
                num_partitions=num_partitions,
                replication_factor=replication_factor
            )
            admin.create_topics([new_topic], validate_only=False)
            self.logger.info(f"Topic {topic} created successfully")
            admin.close()
            return True

        except Exception as e:
            self.logger.error(f"Failed to create topic {topic}: {e}")
            return False



class KafkaTopics:
    """Kafka主题常量定义"""

    CHARGING_POINT_REGISTER = "charging_point_register"
    CHARGING_POINT_HEARTBEAT = "charging_point_heartbeat"
    CHARGING_POINT_STATUS = "charging_point_status"
    CHARGING_POINT_FAULT = "charging_point_fault"

    CHARGING_SESSION_START = "charging_session_start"
    CHARGING_SESSION_DATA = "charging_session_data"
    CHARGING_SESSION_COMPLETE = "charging_session_complete"

    DRIVER_CHARGE_REQUESTS = "driver_charge_requests"  # Driver → Central
    DRIVER_STOP_REQUESTS = "driver_stop_requests"  # Driver → Central
    DRIVER_CPS_REQUESTS = "driver_cps_requests"  # Driver → Central

    DRIVER_RESPONSES = "driver_responses"  # Central → Driver: 


    @staticmethod
    def get_driver_response_topic() -> str:
        """
        Obtener el tema de respuestas para conductores
        Returns:
            str: Tema de respuestas para conductores
        """
        return KafkaTopics.DRIVER_RESPONSES
