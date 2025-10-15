import socket
import threading

import sys
import os
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from Common.CustomLogger import CustomLogger
from Common.MessageFormatter import MessageFormatter


class MySocketServer:
    def __init__(
        self,
        host="0.0.0.0",
        port=5002,
        logger=None,
        message_callback=None,
        disconnect_callback=None,
    ):
        self.host = host
        self.port = port
        self.logger = logger
        self.clients = {}  # {client_id: client_socket}
        self.clients_lock = threading.Lock()  # 用于保护 self.clients 字典的锁

        self.running_event = threading.Event()  # 这个事件控制服务器的主循环

        self.server_socket = None
        self.message_formatter = MessageFormatter()

        if not callable(message_callback):
            raise ValueError("message_callback must be a callable function")
        if not callable(disconnect_callback):
            raise ValueError("disconnect_callback must be a callable function")

        self.message_callback = message_callback  # 用于处理消息的回调函数
        self.disconnect_callback = disconnect_callback  # 用于处理断开连接的回调函数

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1.0)  # 设置 accept 的超时时间

        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)

            self.running_event.set() # 标记服务器正在运行

            # self.logger.info(f"Socket server started on {self.host}:{self.port}")
            # 在这个线程中接受客户端连接
            threading.Thread(target=self._accept_clients, daemon=True).start()
            self.logger.debug(f"Started thread to accept clients, listening on {self.host}:{self.port}")
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            
            self.running_event.clear()  # 标记服务器已停止
            
            if self.server_socket:
                self.server_socket.close()
            raise
    def _accept_clients(self):
        """
        Accept incoming client connections.
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
        Handle communication with a connected client.
        """
        client_id = f"{client_address[0]}:{client_address[1]}"
        self.logger.info(f"Handling client {client_id}")
        with self.clients_lock:
            self.clients[client_id] = client_socket
        
        buffer = b""  # 消息缓冲区

        try:
            while self.running_event.is_set():
                try:

                    data = client_socket.recv(4096)
                    if not data:
                        self.logger.info(f"Client {client_id} disconnected")
                        break
                except socket.timeout:
                    if not self.running_event.is_set():
                        break  # 服务器停止，退出循环
                    continue  # 继续等待数据
                except socket.error as e:
                    self.logger.error(f"Socket error with client {client_id}: {e}")
                    break
                # 将新数据添加到缓冲区
                buffer += data
                self.logger.debug(f"Received raw data from {client_id}: {data}")
                # 处理缓冲区中的完整消息
                while True:
                    buffer, message = self.message_formatter.extract_complete_message(buffer)
                    # self.logger.debug(f"Buffer after extraction: {buffer}")
                    # self.logger.debug(f"Extracted message: {message}")
                    if message is None:
                        self.logger.debug("No complete message found in buffer yet.")
                        break

                    # 处理消息并获取响应
                    # 这里调用的是外部的处理函数
                    response = self.message_callback(client_id, message)
                    self.logger.info(f"Processed message from {client_id}: {message} and got response: {response}")
                    if response:
                        self.send_to_client(client_id, response)
                        self.logger.debug(f"Sent response to {client_id}: {response}")

        except Exception as e:
            self.logger.error(f"Error handling client {client_id}: {e}")
        finally:
            if self.disconnect_callback:
                try:
                    self.disconnect_callback(client_id)
                except Exception as e:
                    self.logger.error(f"Error in disconnect callback for {client_id}: {e}")
            with self.clients_lock:
                if client_id in self.clients:
                    try:
                        self.clients[client_id].close()
                    except Exception as e:
                        self.logger.error(f"Error closing socket for {client_id}: {e}")
                    del self.clients[client_id]



    def send_to_client(self, client_id, message) -> bool:
        """发送消息给特定客户端"""
        with self.clients_lock:
            client_socket = self.clients.get(client_id)
            if client_socket:
                try:
                    packed_message = MessageFormatter.pack_message(message)
                    client_socket.send(packed_message)
                    self.logger.info(f"Sent message to {client_id}: {message}")
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

        with self.clients_lock:
            client_items = list(self.clients.items())  # 复制一份以避免在迭代时修改字典
        for client_id, client_socket in client_items:
            if client_id != exclude_client:
                try:
                    client_socket.send(packed_message)
                    self.logger.info(f"Broadcast to {client_id}: {message}")
                except Exception as e:
                    self.logger.error(f"Error broadcasting to {client_id}: {e}")

    def stop(self):
        """停止服务器"""
        self.logger.info("Stopping socket server...")
        self.running_event.clear()  # 标记服务器停止
        if self.server_socket:
            self.server_socket.close()

        # 向所有客户端发送关闭通知
        shutdown_msg = {"type": "SERVER_SHUTDOWN", "message": "Server is shutting down"}
        self.send_to_all(shutdown_msg)

        with self.clients_lock:
            # 获取所有客户端的列表，防止在迭代时字典被修改
            # 此时，我们不再期望 _handle_client 线程会自己清理，
            # 因为它们可能因为服务器关闭而突然中断。这里是强制清理。
            remaining_client_ids = list(self.clients.keys())
            for client_id in remaining_client_ids:
                try:
                    client_socket = self.clients[client_id]
                    client_socket.close() # 强制关闭 socket
                    del self.clients[client_id] # 从字典中移除
                    self.logger.info(f"Forcibly closed and removed client {client_id} during server shutdown.")
                except Exception as e:
                    self.logger.warning(f"Error during final client cleanup for {client_id}: {e}")
            self.clients.clear() # 确保字典最终为空
        self.logger.info("Socket server stopped")

    def get_connected_clients(self):
        """获取所有连接的客户端"""
        with self.clients_lock:
            return list(self.clients.keys())

    def is_client_connected(self, client_id):
        """检查客户端是否连接"""
        with self.clients_lock:
            return client_id in self.clients


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    server = MySocketServer(host="0.0.0.0", port=8080, logger=logger, message_callback=lambda cid, msg: {"type": "echo", "data": msg}, disconnect_callback=lambda cid: logger.info(f"Client {cid} disconnected"))

    try:
        server.start()
        while (
            server.running_event.is_set()
        ):  
            time.sleep(0.1)  

    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()  # KeyboardInterrupt时调用stop来清理和clear running_event
    except Exception as e:  # 捕获其他意外异常
        logger.error(f"FATAL ERROR in main loop: {e}", exc_info=True)
        server.stop()  # 出错也应该停止服务器
    print("Server stopped.")
