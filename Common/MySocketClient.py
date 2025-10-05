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
            self.socket.connect((host, port))
            self.is_connected = True
            self.logger.info(f"Connected to {host}:{port}")

            # Iniciar thread de recepción
            self.receive_thread = threading.Thread(
                target=self._receive_loop, daemon=True
            )
            self.receive_thread.start()
            return True

        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False

    def _receive_loop(self):
        """Loop para recibir mensajes"""
        while self.is_connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    self.logger.warning("Server disconnected")
                    self.is_connected = False
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
                        self.message_callback(message)
            except KeyboardInterrupt:
                self.logger.info("Receive loop interrupted by user")
                self.is_connected = False
                break

            except Exception as e:
                self.logger.error(f"Error receiving: {e}")
                self.is_connected = False
                break

    def send(self, message):
        """Envía mensaje al servidor"""
        if not self.is_connected:
            self.logger.error("Not connected")
            return False

        try:
            packed = MessageFormatter.pack_message(message)
            self.socket.send(packed)
            return True
        except Exception as e:
            self.logger.error(f"Send failed: {e}")
            return False

    def disconnect(self):
        """Desconecta del servidor"""
        self.is_connected = False
        if self.socket:
            self.socket.close()
