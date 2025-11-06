import socket
import threading

import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from Common.Config.CustomLogger import CustomLogger
from Common.Message.MessageFormatter import MessageFormatter


class MySocketServer:
    def __init__(
        self,
        host="0.0.0.0",
        port=5000,
        logger=None,
        message_callback=None,
        disconnect_callback=None,
    ):
        """
        Inicializar el servidor socket
        Args:
            host: Dirección IP o nombre del host para escuchar
            port: Puerto para escuchar
            logger: Logger personalizado
            message_callback: Función callback para procesar mensajes recibidos
            disconnect_callback: Función callback para manejar desconexiones de clientes
        """
        self.host = host
        self.port = int(port)
        self.logger = logger
        self.clients = {}  # {client_id: client_socket}
        self.clients_lock = threading.Lock() 

        self.running_event = threading.Event()  # Este evento controla el bucle principal del servidor

        self.server_socket = None
        self.message_formatter = MessageFormatter()

        if not callable(message_callback):
            raise ValueError("message_callback must be a callable function")
        if not callable(disconnect_callback):
            raise ValueError("disconnect_callback must be a callable function")

        self.message_callback = message_callback  # Función callback para procesar mensajes recibidos
        self.disconnect_callback = disconnect_callback  # Función callback para manejar desconexiones de clientes

    def start(self):
        """
        Iniciar el servidor socket
        """
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1.0)  # Establecer tiempo de espera para accept

        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)

            self.running_event.set()  # Marcar el servidor como en ejecución

            # self.logger.info(f"Socket server started on {self.host}:{self.port}")
            # Aceptar conexiones de clientes en este hilo
            threading.Thread(target=self._accept_clients, daemon=True).start()
            self.logger.debug(
                f"Started thread to accept clients, listening on {self.host}:{self.port}"
            )
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")

            self.running_event.clear()  # Marcar el servidor como detenido

            if self.server_socket:
                self.server_socket.close()
            raise

    def _accept_clients(self):
        """
        Aceptar conexiones entrantes de clientes.
        """
        while self.running_event.is_set():
            try:
                client_socket, client_address = self.server_socket.accept()
                self.logger.info(f"Accepted connection from {client_address}")

                client_socket.settimeout(1.0)  # 设置 recv 的超时时间

                client_thread = threading.Thread(
                    # 处理与客户端的通信
                    target=self._handle_client,
                    args=(client_socket, client_address),
                    daemon=True,
                )
                client_thread.start()
            except socket.timeout:
                continue  # 超时只是为了检查 running_event，继续循环
            except Exception as e:
                if self.running_event.is_set():  # 仅在服务器运行时记录错误
                    self.logger.error(f"Error accepting clients: {e}")

    def _handle_client(self, client_socket, client_address):
        """
        Manejar la comunicación con un cliente conectado.
        Args:
            client_socket: Socket del cliente
            client_address: Dirección del cliente
        """
        client_id = f"{client_address[0]}:{client_address[1]}"
        self.logger.debug(f"Handling client {client_id}")
        with self.clients_lock:
            self.clients[client_id] = client_socket

        buffer = b"" 

        try:
            while self.running_event.is_set():
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        self.logger.info(f"Client {client_id} disconnected")
                        break
                except socket.timeout:
                    if not self.running_event.is_set():
                        break  
                    continue  
                except ConnectionResetError:
                    self.logger.info(f"Client {client_id} disconnected")
                    break
                except socket.error as e:
                    self.logger.error(f"Socket error with client {client_id}: {e}")
                    break
                except Exception as e:
                    self.logger.error(f"Unexpected error with client {client_id}: {e}")
                    break
                buffer += data
                # self.logger.debug(f"Received raw data from {client_id}: {data}")
                while True:
                    buffer, message = self.message_formatter.extract_complete_message(
                        buffer
                    )
                    # self.logger.debug(f"Buffer after extraction: {buffer}")
                    # self.logger.debug(f"Extracted message: {message}")
                    if message is None:
                        # self.logger.debug("No complete message found in buffer yet.")
                        break

                    # Aqui se llama al callback para procesar el mensaje
                    response = self.message_callback(client_id, message)

                    if response:
                        self.send_to_client(client_id, response)
                        # self.logger.debug(f"Sent response to {client_id}: {response}")

        except Exception as e:
            self.logger.error(f"Error handling client {client_id}: {e}")
        finally:
            if self.disconnect_callback:
                try:
                    self.disconnect_callback(client_id)
                except Exception as e:
                    self.logger.error(
                        f"Error in disconnect callback for {client_id}: {e}"
                    )
            with self.clients_lock:
                if client_id in self.clients:
                    try:
                        self.clients[client_id].close()
                    except Exception as e:
                        self.logger.error(f"Error closing socket for {client_id}: {e}")
                    del self.clients[client_id]

    def send_to_client(self, client_id, message) -> bool:
        """
        Enviar mensaje a un cliente específico
        Args:
            client_id: ID del cliente (formato "ip:port")
            message: Diccionario del mensaje a enviar
        """
        with self.clients_lock:
            client_socket = self.clients.get(client_id)
            if not client_socket:
                self.logger.warning(f"Client {client_id} not connected")
                return False

        try:
            packed_message = MessageFormatter.pack_message(message)
            total_sent = 0

            while total_sent < len(packed_message):
                try:
                    sent = client_socket.send(packed_message[total_sent:])
                    if sent == 0:
                        self.logger.error(
                            f"Socket connection broken with client {client_id}"
                        )
                        return False
                    total_sent += sent
                except socket.timeout:
                    continue

            return True
        except Exception as e:
            self.logger.error(f"Send to client {client_id} failed: {e}")
            return False

    def send_broadcast_message(self, message) -> bool:  
        """
        Enviar mensaje a todos los clientes conectados
        Args:
            message: Diccionario del mensaje a enviar
        Returns:
            bool: Si se envió al menos a un cliente
        """
        if not self.running_event.is_set():
            self.logger.warning("Server is not running, cannot broadcast message.")
            return False

        packed_message = MessageFormatter.pack_message(message)
        sent_to_any_client = False

        with self.clients_lock:
            client_items = list(self.clients.items())

        for client_id, client_socket in client_items:
            try:
                total_sent = 0
                while total_sent < len(packed_message):
                    try:
                        sent = client_socket.send(packed_message[total_sent:])
                        if sent == 0:
                            raise socket.error("Socket connection broken")
                        total_sent += sent
                    except socket.timeout:
                        continue

                self.logger.debug(f"Broadcast to {client_id}: {message.get('type')}")
                sent_to_any_client = True
            except (socket.error, OSError) as e:  
                self.logger.error(
                    f"Error broadcasting to {client_id}: {e}. Removing client.",
                    exc_info=False,
                )  
                # SI el envío falla, eliminar el cliente
                with self.clients_lock:
                    if client_id in self.clients: 
                        try:
                            self.clients[client_id].close()
                        except Exception as close_e:
                            self.logger.warning(
                                f"Error closing socket for {client_id} after send failure: {close_e}"
                            )
                        del self.clients[client_id]
                        if self.disconnect_callback:
                            try:
                                self.disconnect_callback(client_id)
                            except Exception as cb_e:
                                self.logger.error(
                                    f"Error in disconnect callback after broadcast failure for {client_id}: {cb_e}"
                                )
            except Exception as e:
                self.logger.error(
                    f"Unexpected error when broadcasting to {client_id}: {e}",
                    exc_info=True,
                )

        return sent_to_any_client

    def stop(self):
        """
        Detener el servidor socket
        """
        self.logger.debug("Stopping socket server...")
        self.running_event.clear()  # Detener el bucle principal del servidor

        with self.clients_lock:
            for client_id, client_socket in list(self.clients.items()):  
                try:
                    client_socket.shutdown(socket.SHUT_RDWR)  
                    client_socket.close()
                    self.logger.debug(f"Forcibly closed client socket {client_id}.")
                except OSError as e:  
                    self.logger.warning(
                        f"Error shutting down/closing client socket {client_id}: {e}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Unexpected error closing client socket {client_id}: {e}"
                    )
            self.clients.clear() 

        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None  
            self.logger.debug("Server listening socket closed.")

        self.logger.debug("Socket server stopped.")


    def has_active_clients(self) -> bool:
        """
        Verificar si hay clientes conectados
        """
        with self.clients_lock:
            return bool(self.clients)  

    def get_actual_port(self) -> int:
        """
        Obtener el puerto actual en el que el servidor está escuchando
        Cuando el puerto es 0, el sistema asigna un puerto libre automáticamente.
        """
        if self.server_socket:
            return self.server_socket.getsockname()[1]
        return self.port


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    server = MySocketServer(
        host="0.0.0.0",
        port=8080,
        logger=logger,
        message_callback=lambda cid, msg: {"type": "echo", "data": msg},
        disconnect_callback=lambda cid: logger.info(f"Client {cid} disconnected"),
    )

    try:
        server.start()
        while server.running_event.is_set():
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()  # KeyboardInterrupt时调用stop来清理和clear running_event
    except Exception as e:  # 捕获其他意外异常
        logger.error(f"FATAL ERROR in main loop: {e}", exc_info=True)
        server.stop()  # 出错也应该停止服务器
    print("Server stopped.")
