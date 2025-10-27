# Common/MySocketClient.py
import socket
import threading
import time
from Common.Message.MessageFormatter import MessageFormatter
from Common.Config.CustomLogger import CustomLogger


class MySocketClient:
    def __init__(
        self, logger=None, message_callback=None, connect_timeout=30.0, recv_timeout=1.0
    ):
        # 如果没有提供logger，使用默认logger
        if logger is None:
            self.logger = CustomLogger.get_logger()
        else:
            self.logger = logger

        self.socket = None
        self.is_connected = False
        self.buffer = b""
        self.message_callback = message_callback
        self.receive_thread = None

        # 添加Lock保护共享状态
        self._lock = threading.Lock()

        # 可配置的超时时间
        self.connect_timeout = connect_timeout
        self.recv_timeout = recv_timeout

        # Buffer大小限制（1MB）
        self.MAX_BUFFER_SIZE = 1024 * 1024

    def connect(self, host, port):
        """Conecta al servidor"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.connect_timeout)
            self.socket.connect((host, port))
            self.socket.settimeout(self.recv_timeout)

            # 使用Lock设置连接状态
            with self._lock:
                self.is_connected = True

            self.logger.info(f"Connected to {host}:{port}")

            # Iniciar thread de recepción
            self.receive_thread = threading.Thread(
                target=self._receive_loop, daemon=True
            )
            self.receive_thread.start()
            return True
        except socket.timeout:
            self.logger.error(f"Connection timed out: {host}:{port}")
            self._cleanup_socket()
            return False
        except ConnectionRefusedError:
            self.logger.error(f"Connection refused: {host}:{port}")
            self._cleanup_socket()
            return False
        except Exception as e:
            self.logger.error(f"Connection failed: {e} {host}:{port}")
            self._cleanup_socket()
            return False

    def _receive_loop(self):
        """Loop para recibir mensajes"""
        while True:
            # 检查连接状态
            with self._lock:
                if not self.is_connected:
                    break

            try:
                data = self.socket.recv(4096)
                if not data:
                    self.logger.warning("Server disconnected")
                    with self._lock:
                        self.is_connected = False
                    # Notificar la desconexión al callback
                    if self.message_callback:
                        self.message_callback({"type": "CONNECTION_LOST"})
                    break

                self.buffer += data

                # 检查buffer大小，防止溢出
                if len(self.buffer) > self.MAX_BUFFER_SIZE:
                    self.logger.error(
                        f"Buffer overflow: {len(self.buffer)} bytes exceeds limit {self.MAX_BUFFER_SIZE}"
                    )
                    with self._lock:
                        self.is_connected = False
                    break

                # Extraer mensajes completos
                while True:
                    self.buffer, message = MessageFormatter.extract_complete_message(
                        self.buffer
                    )
                    if message is None:
                        break

                    # Callback para procesar mensaje
                    if self.message_callback:
                        try:
                            self.message_callback(message)
                        except Exception as e:
                            self.logger.error(f"Error in message callback: {e}")

            except socket.timeout:
                # Timeout es normal, continuar
                continue
            except (ConnectionResetError, OSError) as e:
                with self._lock:
                    should_log = self.is_connected
                    self.is_connected = False

                if should_log:  # 只有在应该连接时才记录错误
                    self.logger.error(f"Connection error: {e}")
                    if self.message_callback:
                        self.message_callback(
                            {"type": "CONNECTION_ERROR", "error": str(e)}
                        )
                break
            except Exception as e:
                self.logger.error(f"Error receiving: {e}")
                with self._lock:
                    self.is_connected = False
                if self.message_callback:
                    self.message_callback({"type": "CONNECTION_ERROR", "error": str(e)})
                break

    def send(self, message):
        """Envía mensaje al servidor - 处理partial send"""
        with self._lock:
            if not self.is_connected:
                self.logger.error("Not connected")
                return False

            if self.socket is None:
                self.logger.error("Socket is None")
                return False

        try:
            # 直接打包JSON消息
            packed = MessageFormatter.pack_message(message)
            total_sent = 0

            # 循环发送直到完整
            while total_sent < len(packed):
                try:
                    sent = self.socket.send(packed[total_sent:])
                    if sent == 0:
                        self.logger.error("Socket connection broken")
                        with self._lock:
                            self.is_connected = False
                        return False
                    total_sent += sent
                except socket.timeout:
                    # 超时，继续尝试
                    continue

            return True
        except Exception as e:
            self.logger.error(f"Send failed: {e}")
            with self._lock:
                self.is_connected = False
            return False

    def _cleanup_socket(self):
        """清理socket资源"""
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except (OSError, socket.error):
                pass  # Socket可能已关闭

            try:
                self.socket.close()
            except (OSError, socket.error):
                pass

            self.socket = None

    def disconnect(self):
        """Desconecta del servidor - 安全的断开连接"""
        with self._lock:
            if not self.is_connected:
                return
            self.is_connected = False

        # 清理socket
        self._cleanup_socket()

        # 等待接收线程结束
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2)
            if self.receive_thread.is_alive():
                self.logger.warning("Receive thread did not terminate in time")

        self.logger.info("Disconnected from server")
