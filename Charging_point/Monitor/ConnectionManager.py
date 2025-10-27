import threading
import time
import queue
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from Common.Network.MySocketClient import MySocketClient
from Common.Config.CustomLogger import CustomLogger


class ConnectionManager:
    """
    负责维护一个可靠的、自动重连的SocketClient连接。
    它处理连接/断开/重试，并通过回调通知上层应用连接状态和接收到的消息。
    """

    def __init__(
        self,
        host,
        port,
        name,
        logger,
        message_ingress_callback,
        connection_status_callback,
    ):
        if not logger:
            self.logger = CustomLogger.get_logger()
        else:
            self.logger = logger
        self.host = host
        self.port = port
        self.name = name  # 例如 "Central" 或 "Engine"，用于日志标识
        self._message_ingress_callback = (
            message_ingress_callback  # 接收到消息时调用的回调函数
        )
        self._connection_status_callback = (
            connection_status_callback  # 连接状态改变时调用的回调函数
        )

        self._client = MySocketClient(
            logger=self.logger, message_callback=self._process_incoming_socket_message
        )

        self._connected = False  # 内部连接状态标志
        self._running = False
        self._reconnect_thread = None
        self.RECONNECT_INTERVAL = 5  # 连接重试间隔（秒）

    @property
    def is_connected(self):
        """
        返回当前连接管理器是否认为自己已连接 (并且底层SocketClient也认为已连接)。
        """
        return self._connected and self._client.is_connected

    def _process_incoming_socket_message(self, message):
        """
        底层MySocketClient接收到消息后的内部处理函数。
        这里我们捕获连接断开的特殊消息，并更新状态。
        """
        # 消息已经是字典格式（JSON）
        msg_type = message.get("type")
        if msg_type == "CONNECTION_LOST" or msg_type == "SERVER_SHUTDOWN":
            self.logger.warning(
                f"[{self.name}] Connection lost or detected server shutdown."
            )
            if self._connected:  # 如果之前是连接状态，才报告断开
                self._connected = False
                self._connection_status_callback(self.name, "DISCONNECTED")
            # 重连逻辑会在 _run_reconnect_loop 中自动触发
        else:
            # 其他正常应用消息，转发给上层应用 (EV_CP_M)
            self._message_ingress_callback(self.name, message)

    def start(self):
        """
        启动连接管理器。它将在一个守护线程中自动尝试连接和重连。
        """
        if not self._running:
            self._running = True
            # 使用守护线程，确保主程序退出时这些线程会被强制终止
            self._reconnect_thread = threading.Thread(
                target=self._run_reconnect_loop,
                daemon=True,
                name=f"{self.name}CM_Thread",
            )
            self._reconnect_thread.start()
            self.logger.info(f"[{self.name}] ConnectionManager started.")

    def stop(self):
        """
        停止连接管理器。会尝试优雅地停止内部重连线程并断开所有连接。
        """
        try:

            if self._running:
                self.logger.info(f"[{self.name}] Stopping ConnectionManager.")
                self._running = False
                if self._reconnect_thread:
                    self._reconnect_thread.join(timeout=5)  # 给线程一点时间自己退出
                    if self._reconnect_thread.is_alive():
                        self.logger.warning(
                            f"[{self.name}] ConnectionManager thread did not terminate gracefully."
                        )
                self._client.disconnect()  # 确保底层socket客户端断开连接
                self.logger.info(f"[{self.name}] ConnectionManager stopped.")
        except KeyboardInterrupt:
            pass
        except Exception as e:
            self.logger.error(f"[{self.name}] Error stopping ConnectionManager: {e}")

    def send(self, message):
        """
        如果已连接，则通过MySocketClient发送消息。
        """
        if self.is_connected:
            return self._client.send(message)
        else:
            self.logger.warning(
                f"[{self.name}] Not connected, cannot send message: {message.get('type', 'N/A')}"
            )
            return False

    def _run_reconnect_loop(self):
        """
        连接管理器的核心循环：负责连接、断开检测和自动重连。
        """
        while self._running:
            if not self.is_connected:
                self.logger.info(
                    f"[{self.name}] Attempting to connect to {self.host}:{self.port}..."
                )
                if self._client.connect(self.host, self.port):
                    self._connected = True
                    self.logger.info(f"[{self.name}] Successfully connected.")
                    self._connection_status_callback(self.name, "CONNECTED")
                else:
                    self.logger.error(
                        f"[{self.name}] Connection failed. Retrying in {self.RECONNECT_INTERVAL}s."
                    )
                    time.sleep(self.RECONNECT_INTERVAL)
            else:
                # 如果已连接，就让MySocketClient自己处理消息接收。
                # _process_incoming_socket_message 会处理底层断开事件。
                time.sleep(1)  # 每秒检查一次是否需要重连或停止

        # 循环结束时，确保客户端断开
        self._client.disconnect()
        self.logger.info(f"[{self.name}] Reconnect loop terminated.")

# Charging point instasnce how many have ?
# Message formatter should be string cointaning # to seperate?
# 