# Common/MySocketClient.py
import socket
import threading
import time
from Common.MessageFormatter import MessageFormatter


class MySocketClient:
    def __init__(self, logger=None, message_callback=None):
        self.logger = logger
        self.socket = None
        self.is_connected = False
        self.buffer = b""
        self.message_callback = message_callback
        self.receive_thread = None

    def connect(self, host, port):
        """Conecta al servidor"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30.0)  # Timeout de 30 segundos
            self.socket.connect((host, port))
            self.socket.settimeout(1.0)  # Timeout más corto para recv
            self.is_connected = True
            self.logger.info(f"Connected to {host}:{port}")

            # Iniciar thread de recepción
            self.receive_thread = threading.Thread(
                target=self._receive_loop, daemon=True
            )
            self.receive_thread.start()
            return True

        except Exception as e:
            self.logger.error(f"Connection failed: {e} {host}:{port}")
            
            if self.socket:
                self.socket.close()
                self.socket = None
            return False

    def _receive_loop(self):
        """Loop para recibir mensajes"""
        while self.is_connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    self.logger.warning("Server disconnected")
                    self.is_connected = False
                    # Notificar la desconexión al callback
                    if self.message_callback:
                        self.message_callback({"type": "CONNECTION_LOST"})
                    break

                self.buffer += data

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
                if self.is_connected:  # 只有在应该连接时才记录错误
                    self.logger.error(f"Connection error: {e}")
                    self.is_connected = False
                    if self.message_callback:
                        self.message_callback(
                            {"type": "CONNECTION_ERROR", "error": str(e)}
                        )
                break
            except Exception as e:
                self.logger.error(f"Error receiving: {e}")
                self.is_connected = False
                if self.message_callback:
                    self.message_callback({"type": "CONNECTION_ERROR", "error": str(e)})
                break

    def send(self, message):
        """Envía mensaje al servidor"""
        if not self.is_connected:
            self.logger.error("Not connected")
            return False

        try:
            packed = MessageFormatter.pack_message(message)
            self.socket.send(packed)
            # self.logger.debug(f"Sent message: {packed}")
            return True
        except Exception as e:
            self.logger.error(f"Send failed: {e}")
            return False

    def disconnect(self):
        """Desconecta del servidor"""
        if not self.is_connected:
            return

        self.is_connected = False
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
            except:
                pass  # Socket ya cerrado
            self.socket = None

        # Esperar a que termine el thread de recepción
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2)

        self.logger.info("Disconnected from server")
