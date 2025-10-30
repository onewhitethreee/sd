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
        port=5002,
        logger=None,
        message_callback=None,
        disconnect_callback=None,
    ):
        self.host = host
        self.port = int(port)
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

            self.running_event.set()  # 标记服务器正在运行

            # self.logger.info(f"Socket server started on {self.host}:{self.port}")
            # 在这个线程中接受客户端连接
            threading.Thread(target=self._accept_clients, daemon=True).start()
            self.logger.debug(
                f"Started thread to accept clients, listening on {self.host}:{self.port}"
            )
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
                except ConnectionResetError:
                    self.logger.info(f"Client {client_id} disconnected")
                    break
                except socket.error as e:
                    self.logger.error(f"Socket error with client {client_id}: {e}")
                    break
                except Exception as e:
                    self.logger.error(f"Unexpected error with client {client_id}: {e}")
                    break
                # 将新数据添加到缓冲区
                buffer += data
                # self.logger.debug(f"Received raw data from {client_id}: {data}")
                # 处理缓冲区中的完整消息
                while True:
                    buffer, message = self.message_formatter.extract_complete_message(
                        buffer
                    )
                    # self.logger.debug(f"Buffer after extraction: {buffer}")
                    # self.logger.debug(f"Extracted message: {message}")
                    if message is None:
                        # self.logger.debug("No complete message found in buffer yet.")
                        break

                    # 处理消息并获取响应
                    # 这里调用的是外部的处理函数
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
        """发送消息给特定客户端 - 处理partial send"""
        with self.clients_lock:
            client_socket = self.clients.get(client_id)
            if not client_socket:
                self.logger.warning(f"Client {client_id} not connected")
                return False

        try:
            packed_message = MessageFormatter.pack_message(message)
            total_sent = 0

            # 循环发送直到完整
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
                    # 超时，继续尝试
                    continue

            return True
        except Exception as e:
            self.logger.error(f"Send to client {client_id} failed: {e}")
            return False

    def send_broadcast_message(self, message) -> bool:  # 返回是否成功广播（至少一个）
        """向所有连接的客户端广播消息 - 处理partial send"""
        if not self.running_event.is_set():
            self.logger.warning("Server is not running, cannot broadcast message.")
            return False

        # 直接打包JSON消息
        packed_message = MessageFormatter.pack_message(message)
        sent_to_any_client = False

        # 使用一个副本，以便安全地在迭代中修改 clients
        with self.clients_lock:
            client_items = list(self.clients.items())

        for client_id, client_socket in client_items:
            try:
                total_sent = 0
                # 循环发送直到完整
                while total_sent < len(packed_message):
                    try:
                        sent = client_socket.send(packed_message[total_sent:])
                        if sent == 0:
                            raise socket.error("Socket connection broken")
                        total_sent += sent
                    except socket.timeout:
                        # 超时，继续尝试
                        continue

                self.logger.debug(f"Broadcast to {client_id}: {message.get('type')}")
                sent_to_any_client = True
            except (socket.error, OSError) as e:  # 捕获更具体的socket错误
                self.logger.error(
                    f"Error broadcasting to {client_id}: {e}. Removing client.",
                    exc_info=False,
                )  # 不需要完整堆栈
                # 如果发送失败，说明连接可能已死，进行清理
                with self.clients_lock:
                    if client_id in self.clients:  # 再次检查以防其他线程已清理
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
        """停止服务器"""
        self.logger.info("Stopping socket server...")
        self.running_event.clear()  # 标记服务器停止

        with self.clients_lock:
            for client_id, client_socket in list(self.clients.items()):  # 迭代副本
                try:
                    client_socket.shutdown(socket.SHUT_RDWR)  # 尝试优雅关闭
                    client_socket.close()
                    self.logger.debug(f"Forcibly closed client socket {client_id}.")
                except OSError as e:  # 捕获操作系统级别的关闭错误
                    self.logger.warning(
                        f"Error shutting down/closing client socket {client_id}: {e}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Unexpected error closing client socket {client_id}: {e}"
                    )
            self.clients.clear()  # 清空客户端字典

        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None  # 清空引用
            self.logger.info("Server listening socket closed.")

        self.logger.info("Socket server stopped.")

    def get_connected_clients(self):
        """获取所有连接的客户端"""
        with self.clients_lock:
            return list(self.clients.keys())

    def is_client_connected(self, client_id):
        """检查客户端是否连接"""
        with self.clients_lock:
            return client_id in self.clients

    def has_active_clients(self) -> bool:
        """
        检查当前是否有活跃的客户端连接。
        """
        with self.clients_lock:
            return bool(self.clients)  # 直接返回字典是否为空的布尔值

    def _simulate_client_connect(self, client_id):
        """
        模拟客户端连接（用于调试）。
        这个方法创建一个虚拟的客户端连接，用于测试消息处理。
        """
        try:
            self.logger.info(f"Simulating client connection: {client_id}")

            # 创建一个虚拟的socket对象（不是真实的socket）
            # 这用于模拟客户端存在
            with self.clients_lock:
                if client_id not in self.clients:
                    # 创建一个占位符对象，表示客户端已连接
                    # 在实际应用中，这会是一个真实的socket
                    self.clients[client_id] = None  # 使用None作为占位符
                    self.logger.info(f"Client {client_id} simulated connection added")
                else:
                    self.logger.warning(f"Client {client_id} already connected")
        except Exception as e:
            self.logger.error(f"Error simulating client connection: {e}")

    def _simulate_client_disconnect(self, client_id):
        """
        模拟客户端断开连接（用于调试）。
        这个方法移除虚拟的客户端连接，并触发断开连接回调。
        """
        try:
            self.logger.info(f"Simulating client disconnection: {client_id}")

            with self.clients_lock:
                if client_id in self.clients:
                    del self.clients[client_id]
                    self.logger.info(
                        f"Client {client_id} simulated disconnection removed"
                    )
                else:
                    self.logger.warning(
                        f"Client {client_id} not found in connected clients"
                    )

            # 触发断开连接回调
            if self.disconnect_callback:
                try:
                    self.disconnect_callback(client_id)
                    self.logger.info(f"Disconnect callback executed for {client_id}")
                except Exception as e:
                    self.logger.error(
                        f"Error in disconnect callback for {client_id}: {e}"
                    )
        except Exception as e:
            self.logger.error(f"Error simulating client disconnection: {e}")


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
