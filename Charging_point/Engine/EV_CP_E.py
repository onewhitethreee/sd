"""
Módulo que recibe la información de los sensores y se conecta al sistema monitor
"""

import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.ConfigManager import ConfigManager
from Common.CustomLogger import CustomLogger
from Common.MySocketServer import MySocketServer
from Common.Status import Status


class EV_CP_E:
    def __init__(self, logger=None):
        self.logger = logger
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()

        if not self.debug_mode:
            self.tools = AppArgumentParser(
                "EV_CP_E", "Módulo de gestión de sensores y comunicación con la monitor"
            )
            self.tools.add_argument(
                "broker",
                type=ip_port_type,
                help="IP y puerto del Broker/Bootstrap-server (formato IP:PORT)",
            )
            self.args = self.tools.parse_args()
        else:

            class Args:
                broker = self.config.get_broker()

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        # 从配置获取Engine监听地址
        self.engine_listen_address = self.config.get_ip_port_ev_cp_e()

        self.running = False
        self.is_charging = False
        self.monitor_server = None

    def get_current_status(self):
        """返回Engine当前状态"""
        if self.is_charging:
            return Status.CHARGING.value
        elif not self.running:
            return Status.FAULTY.value
        else:
            return Status.ACTIVE.value

    def _process_monitor_message(self, client_id, message):
        """处理来自Monitor的消息"""
        try:
            msg_type = message.get("type")
            self.logger.debug(f"Received message from Monitor {client_id}: {msg_type}")

            response = None

            if msg_type == "health_check_request":
                response = self._handle_health_check(message)
            elif msg_type == "stop_command":
                response = self._handle_stop_command(message)
            elif msg_type == "resume_command":
                response = self._handle_resume_command(message)
            else:
                self.logger.warning(f"Unknown message type from Monitor: {msg_type}")
                response = {
                    "type": "error_response",
                    "message_id": message.get("message_id"),
                    "error": "Unknown message type",
                }

            # 返回响应，MySocketServer会自动发送给客户端
            return response

        except Exception as e:
            self.logger.error(f"Error processing monitor message: {e}")
            return {
                "type": "error_response",
                "message_id": message.get("message_id"),
                "error": str(e),
            }

    def _handle_health_check(self, message):
        """处理健康检查请求"""
        self.logger.debug("Processing health check from Monitor")

        response = {
            "type": "health_check_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "engine_status": self.get_current_status(),
            "timestamp": int(time.time()),
            "is_charging": self.is_charging,
        }

        self.logger.debug(f"Health check response prepared {response}")
        return response

    def _handle_stop_command(self, message):
        """处理停止命令"""
        self.logger.info("Received stop command from Monitor")

        if self.is_charging:
            self._stop_charging_session(ev_id=None)

        response = {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "message": "Stop command executed",
        }
        return response

    def _handle_resume_command(self, message):
        """处理恢复命令"""
        self.logger.info("Received resume command from Monitor")
        # TODO: 实现恢复逻辑

        response = {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "message": "Resume command executed",
        }
        return response

    def _handle_monitor_disconnect(self, client_id):
        """处理Monitor断开连接"""
        self.logger.warning(f"Monitor {client_id} disconnected")
        # TODO: 可能需要进入某种安全模式或者尝试重连

    def _start_monitor_server(self):
        """启动服务器等待Monitor连接 """
        try:
            self.monitor_server = MySocketServer(
                host=self.engine_listen_address[0],
                port=self.engine_listen_address[1],
                logger=self.logger,
                message_callback=self._process_monitor_message,  
                disconnect_callback=self._handle_monitor_disconnect,
            )

            self.monitor_server.start()  
            self.logger.info(
                f"Monitor server started on {self.engine_listen_address[0]}:{self.engine_listen_address[1]}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error starting monitor server: {e}")
            return False

    def _init_connections(self):
        """初始化连接"""
        try:
            if not self._start_monitor_server():
                raise Exception("Failed to start monitor server")

            # TODO: 初始化Kafka客户端
            self.logger.info(
                f"Will connect to broker at {self.args.broker[0]}:{self.args.broker[1]}"
            )

            self.running = True
            return True

        except Exception as e:
            self.logger.error(f"Error initializing connections: {e}")
            return False

    def _shutdown_system(self):
        """关闭系统"""
        self.logger.info("Starting system shutdown...")
        self.running = False

        if self.is_charging:
            self._stop_charging_session(ev_id=None)
            self.is_charging = False

        if self.monitor_server:
            self.monitor_server.stop()  # 使用现有的stop()方法

        self.logger.info("System shutdown complete")

    def _start_charging_session(self, ev_id):
        """启动充电会话"""
        self.logger.info(f"Starting charging session for EV: {ev_id}")
        self.is_charging = True
        # TODO: 实现充电启动逻辑

    def _stop_charging_session(self, ev_id):
        """停止充电会话"""
        self.logger.info(f"Stopping charging session for EV: {ev_id}")
        self.is_charging = False
        # TODO: 实现充电停止逻辑

    def initialize_system(self):
        """初始化系统"""
        self.logger.info("Initializing EV_CP_E module")
        return self._init_connections()

    def start(self):
        self.logger.info("Starting EV_CP_E module")
        self.logger.info(
            f"Will listen for Monitor on {self.engine_listen_address[0]}:{self.engine_listen_address[1]}"
        )
        self.logger.info(
            f"Will connect to Broker at {self.args.broker[0]}:{self.args.broker[1]}"
        )

        if not self.initialize_system():
            self.logger.error("Failed to initialize system")
            sys.exit(1)

        try:
            while self.running:
                time.sleep(1)  # 保持运行

        except KeyboardInterrupt:
            self.logger.info("Shutting down EV_CP_E")
            self._shutdown_system()
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self._shutdown_system()


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    ev_cp_e = EV_CP_E(logger=logger)
    ev_cp_e.start()
