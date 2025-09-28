import socket
import threading
import json
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from Common.CustomLogger import CustomLogger
from Common.MessageFormatter import MessageFormatter


class MySocketServer:
    def __init__(self, host="0.0.0.0", port=8080, logger=None):
        self.host = host
        self.port = port
        self.logger = logger
        self.server_socket = None
        self.is_running = False
        self.message_formatter = MessageFormatter()
        self.clients = {}  # {client_id: client_socket}

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.is_running = True
        self.logger.info(f"Socket server started on {self.host}:{self.port}")

        # 在这个线程中接受客户端连接
        threading.Thread(target=self._accept_clients, daemon=True).start()
        self.logger.debug(f"Started thread to accept clients, listening on {self.host}:{self.port}")
    def _accept_clients(self):
        """
        Accept incoming client connections.
        """
        while self.is_running:
            try:
                client_socket, client_address = self.server_socket.accept()
                self.logger.info(f"Accepted connection from {client_address}")
                client_thread = threading.Thread(
                    # 处理与客户端的通信
                    target=self._handle_client,
                    args=(client_socket, client_address),
                    daemon=True,
                )
                client_thread.start()
            except Exception as e:
                if self.is_running:  
                    self.logger.error(f"Error accepting clients: {e}")

    def _handle_client(self, client_socket, client_address):
        """
        Handle communication with a connected client.
        """
        client_id = f"{client_address[0]}:{client_address[1]}"
        self.logger.info(f"Handling client {client_id}")
        self.clients[client_id] = client_socket
        buffer = b""  # 消息缓冲区

        try:
            while self.is_running:
                data = client_socket.recv(4096)
                if not data:
                    self.logger.info(f"Client {client_id} disconnected")
                    break

                # 将新数据添加到缓冲区
                buffer += data
                self.logger.debug(f"Received raw data from {client_id}: {data}")
                # 处理缓冲区中的完整消息
                while True:
                    buffer, message = self.message_formatter.extract_complete_message(buffer)
                    self.logger.debug(f"Buffer after extraction: {buffer}")
                    self.logger.debug(f"Extracted message: {message}")
                    if message is None:
                        self.logger.debug("No complete message found in buffer yet.")
                        break

                    # 处理消息并获取响应
                    # TODO 搞懂这里的_process_message是怎么个事
                    response = self._process_message(client_id, message)
                    self.logger.debug(f"Processed message from {client_id}: {message}")
                    if response:
                        self.send_to_client(client_id, response)
                        self.logger.debug(f"Sent response to {client_id}: {response}")

        except Exception as e:
            self.logger.error(f"Error handling client {client_id}: {e}")
        finally:
            if client_id in self.clients:
                # 清理客户端连接
                del self.clients[client_id]
            client_socket.close()
            self.logger.info(f"Connection closed for {client_id}")

    def _process_message(self, client_id, message):
        # TODO 这里添加注册的逻辑
        """处理接收到的消息并返回响应"""
        self.logger.info(f"Processing message from {client_id}: {message}")
        msg_type = message.get("type")

        if msg_type == "PING":
            return {"type": "PONG", "timestamp": message.get("timestamp")}

        elif msg_type == "ECHO":
            return {"type": "ECHO_REPLY", "data": message.get("data")}

        elif msg_type == "REGISTER" or msg_type == 'register':
            self.logger.debug(f"Client {client_id} registered as {message.get('name')}")
            return {"type": "REGISTER_ACK", "status": "success"}

        else:
            self.logger.warning(f"Unknown message type: {msg_type}")
            return {"type": "ERROR", "message": f"Unknown message type: {msg_type}"}

    def send_to_client(self, client_id, message) -> bool:
        """发送消息给特定客户端"""
        if client_id in self.clients:
            try:
                packed_message = MessageFormatter.pack_message(message)
                self.clients[client_id].send(packed_message)
                self.logger.info(f"Sent message to {client_id}: {packed_message}")
                return True
            except Exception as e:
                self.logger.error(f"Error sending message to {client_id}: {e}")
                return False
        else:
            self.logger.warning(f"Client {client_id} not connected")
            return False

    def send_to_all(self, message, exclude_client=None):
        """向所有客户端广播消息"""
        packed_message = MessageFormatter.pack_message(message)
        for client_id, client_socket in self.clients.items():
            if client_id != exclude_client:
                try:
                    client_socket.send(packed_message)
                    self.logger.info(f"Broadcast to {client_id}: {message}")
                except Exception as e:
                    self.logger.error(f"Error broadcasting to {client_id}: {e}")

    def stop(self):
        """停止服务器"""
        # TODO 在发送关闭通知前，确保所有消息都已处理完毕，等待所有客户端的确认

        self.is_running = False

        # 向所有客户端发送关闭通知
        shutdown_msg = {"type": "SERVER_SHUTDOWN"}
        self.send_to_all(shutdown_msg)

        # 关闭所有连接
        for client_id in list(self.clients.keys()):
            self._disconnect_client(client_id)

        if self.server_socket:
            self.server_socket.close()

        self.logger.info("Socket server stopped")

    def _disconnect_client(self, client_id):
        """断开特定客户端"""
        if client_id in self.clients:
            try:
                self.clients[client_id].close()
            except:
                pass
            del self.clients[client_id]

    def get_connected_clients(self):
        """获取所有连接的客户端"""
        return list(self.clients.keys())

    def is_client_connected(self, client_id):
        """检查客户端是否连接"""
        return client_id in self.clients


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    server = MySocketServer(host="0.0.0.0", port=8080, logger=logger)

    try:
        server.start()
        # 保持主线程运行
        while True:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()
