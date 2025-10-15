"""
你的 _process_charging_point_message 逻辑非常好，这是这个类中少有的亮点。把它提取出来，作为一个独立的 MessageDispatcher 类。
EV_Central 的 _process_charging_point_message 只需要把消息转发给这个 MessageDispatcher。
MessageDispatcher 内部维护 handlers 字典。
"""


# message_dispatcher.py
class MessageDispatcher:
    def __init__(self, registry, session_manager, socket_server, logger):
        self.registry = registry
        self.session_manager = session_manager
        self.socket_server = socket_server  # 用于发送响应
        self.logger = logger
        self.handlers = {
            "register_request": self._handle_register,
            "heartbeat_request": self._handle_heartbeat,
            # ... 等等
        }

    def _handle_register(self, client_id, message):
        cp_id = message.get("id")
        # 直接调用 registry 的方法
        # self.registry.register_or_update_cp(...)
        # 并构造响应
        # self.socket_server.send_message_to_client(...)
        pass

    # ... 其他所有消息处理逻辑
