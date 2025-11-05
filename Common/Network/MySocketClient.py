import socket
import threading
from Common.Message.MessageFormatter import MessageFormatter
from Common.Config.CustomLogger import CustomLogger


class MySocketClient:
    def __init__(
        self, logger=None, message_callback=None, connect_timeout=30.0, recv_timeout=1.0
    ):
        """
        Inicializar el cliente socket
        Args:
            logger: Logger personalizado (opcional)
            message_callback: Función callback para procesar mensajes recibidos
            connect_timeout: Tiempo de espera para la conexión
            recv_timeout: Tiempo de espera para recepción de datos
        """
        if logger is None:
            self.logger = CustomLogger.get_logger()
        else:
            self.logger = logger

        self.socket = None
        self.is_connected = False
        self.buffer = b""
        self.message_callback = message_callback
        self.receive_thread = None

        self._lock = threading.Lock()

        self.connect_timeout = connect_timeout
        self.recv_timeout = recv_timeout

        self.MAX_BUFFER_SIZE = 1024 * 1024

    def connect(self, host, port):
        """
        Conecta al servidor
        Args:
            host: Dirección IP o nombre del host del servidor
            port: Puerto del servidor
        Returns:
            bool: Si la conexión fue exitosa
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.connect_timeout)
            self.socket.connect((host, port))
            self.socket.settimeout(self.recv_timeout)

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
        """
        Bucle para recibir datos del servidor
        """
        while True:
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

                # Comprobar el tamaño del buffer para evitar desbordamientos
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

                if should_log:  # Solo registrar errores si se estaba conectado
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
        """Envía mensaje al servidor 
        Args:
            message: Diccionario del mensaje a enviar

        Returns:
            bool: Si el envío fue exitoso
        """
        with self._lock:
            if not self.is_connected:
                self.logger.error("Not connected")
                return False

            if self.socket is None:
                self.logger.error("Socket is None")
                return False

        try:
            packed = MessageFormatter.pack_message(message)
            total_sent = 0

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
                    continue

            return True
        except Exception as e:
            self.logger.error(f"Send failed: {e}")
            with self._lock:
                self.is_connected = False
            return False

    def _cleanup_socket(self):
        """Limpiar recursos del socket"""
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except (OSError, socket.error):
                pass  # El socket puede que ya esté cerrado

            try:
                self.socket.close()
            except (OSError, socket.error):
                pass

            self.socket = None

    def disconnect(self):
        """Desconecta del servidor """
        with self._lock:
            if not self.is_connected:
                return
            self.is_connected = False

        self._cleanup_socket()

        # Esperar a que termine el hilo de recepción
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2)
            if self.receive_thread.is_alive():
                self.logger.warning("Receive thread did not terminate in time")

        self.logger.info("Disconnected from server")
