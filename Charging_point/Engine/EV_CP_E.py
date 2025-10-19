"""
Módulo que recibe la información de los sensores y se conecta al sistema monitor
"""

import sys
import os
import time
import threading
import uuid
import random

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
        self.current_session = None
        self.charging_thread = None
        self.charging_data = {
            "energy_consumed": 0.0,
            "total_cost": 0.0,
            "charging_rate": 0.0,  # kWh per second
            "price_per_kwh": 0.20
        }

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
            elif msg_type == "start_charging_command":
                response = self._handle_start_charging_command(message)
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
        # self.logger.debug("Processing health check from Monitor")

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
        
        # 实现恢复逻辑
        if not self.running:
            self.running = True
            self.logger.info("Engine resumed operation")
        
        # 如果当前状态是故障，重置为活跃
        if self.get_current_status() == Status.FAULTY.value:
            self.logger.info("Engine status reset from FAULTY to ACTIVE")

        response = {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success",
            "message": "Resume command executed",
        }
        return response

    def _handle_start_charging_command(self, message):
        """处理开始充电命令"""
        self.logger.info("Received start charging command from Monitor")
        
        ev_id = message.get("ev_id", "unknown_ev")
        driver_id = message.get("driver_id")
        session_id = message.get("session_id")
        
        if self.is_charging:
            return {
                "type": "command_response",
                "message_id": message.get("message_id"),
                "status": "failure",
                "message": "Already charging",
            }
        
        #success = self._start_charging_session(ev_id)
        success = self._start_charging_session(ev_id, driver_id)

        if success and session_id:
            # 更新会话ID
            if self.current_session:
                self.current_session["session_id"] = session_id
        
        response = {
            "type": "command_response",
            "message_id": message.get("message_id"),
            "status": "success" if success else "failure",
            "message": "Charging started" if success else "Failed to start charging",
            "session_id": self.current_session["session_id"] if self.current_session else None
        }
        return response

    def _handle_monitor_disconnect(self, client_id):
        """处理Monitor断开连接"""
        self.logger.warning(f"Monitor {client_id} disconnected")
        
        # 进入安全模式：停止当前充电会话
        if self.is_charging:
            self.logger.warning("Monitor disconnected during charging - stopping charging session for safety")
            self._stop_charging_session(ev_id=None)
        
        # 设置状态为故障，等待Monitor重连
        self.logger.warning("Engine entering fault mode due to monitor disconnection")

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

    def _start_charging_session(self, ev_id, driver_id=None):
        """启动充电会话"""
        self.logger.info(f"Starting charging session for EV: {ev_id}")
        
        if self.is_charging:
            self.logger.warning("Already charging, cannot start new session")
            return False
            
        self.is_charging = True
        self.current_session = {
            "session_id": str(uuid.uuid4()),
            "ev_id": ev_id,
            "driver_id": driver_id or ev_id,
            "start_time": time.time(),
            "energy_consumed": 0.0,
            "total_cost": 0.0
        }
        
        # 重置充电数据
        self.charging_data["energy_consumed"] = 0.0
        self.charging_data["total_cost"] = 0.0
        self.charging_data["charging_rate"] = random.uniform(0.1, 0.3)  # 随机充电速率
        
        # 启动充电线程
        self.charging_thread = threading.Thread(target=self._charging_process, daemon=True)
        self.charging_thread.start()
        
        self.logger.info(f"Charging session {self.current_session['session_id']} started")
        return True

    def _stop_charging_session(self, ev_id):
        """停止充电会话"""
        self.logger.info(f"Stopping charging session for EV: {ev_id}")
        
        if not self.is_charging:
            self.logger.warning("No active charging session to stop")
            return False
            
        self.is_charging = False
        
        if self.current_session:
            # 计算最终数据
            end_time = time.time()
            duration = end_time - self.current_session["start_time"]
            
            self.current_session["end_time"] = end_time
            self.current_session["duration"] = duration
            self.current_session["energy_consumed"] = self.charging_data["energy_consumed"]
            self.current_session["total_cost"] = self.charging_data["total_cost"]
            
            self.logger.info(f"Charging session {self.current_session['session_id']} completed:")
            self.logger.info(f"  Duration: {duration:.1f} seconds")
            self.logger.info(f"  Energy consumed: {self.charging_data['energy_consumed']:.2f} kWh")
            self.logger.info(f"  Total cost: €{self.charging_data['total_cost']:.2f}")
            
            # 发送充电完成通知到Monitor
            self._send_charging_completion()
            
            self.current_session = None
        
        return True

    def _charging_process(self):
        """充电过程模拟"""
        self.logger.info("Charging process started")
        
        while self.is_charging and self.running:
            try:
                # 模拟充电数据更新（每秒）
                time.sleep(1)
                
                if not self.is_charging:
                    break
                
                # 计算这一秒消耗的电量
                energy_this_second = self.charging_data["charging_rate"] / 3600  # 转换为kWh
                self.charging_data["energy_consumed"] += energy_this_second
                
                # 计算费用
                self.charging_data["total_cost"] = (
                    self.charging_data["energy_consumed"] * self.charging_data["price_per_kwh"]
                )
                
                # 更新会话数据
                if self.current_session:
                    self.current_session["energy_consumed"] = self.charging_data["energy_consumed"]
                    self.current_session["total_cost"] = self.charging_data["total_cost"]
                
                # 发送充电数据到Monitor
                self._send_charging_data()
                
                self.logger.debug(f"Charging progress: {self.charging_data['energy_consumed']:.3f} kWh, €{self.charging_data['total_cost']:.2f}")
                
            except Exception as e:
                self.logger.error(f"Error in charging process: {e}")
                break
        
        self.logger.info("Charging process ended")

    def _send_charging_data(self):
        """发送充电数据到Monitor"""
        if not self.monitor_server or not self.current_session:
            return
            
        charging_data_message = {
            "type": "charging_data",
            "message_id": str(uuid.uuid4()),
            "session_id": self.current_session["session_id"],
            "energy_consumed_kwh": round(self.charging_data["energy_consumed"], 3),
            "total_cost": round(self.charging_data["total_cost"], 2),
            "charging_rate": self.charging_data["charging_rate"],
            "timestamp": int(time.time())
        }
        
        # 通过Monitor服务器发送给连接的Monitor客户端
        try:
            if self.monitor_server and hasattr(self.monitor_server, 'clients') and self.monitor_server.clients:
                for client_id in self.monitor_server.clients.keys():
                    self.monitor_server.send_message_to_client(client_id, charging_data_message)
                self.logger.debug(f"Charging data sent to Monitor: {charging_data_message}")
        except Exception as e:
            self.logger.error(f"Failed to send charging data to Monitor: {e}")

    def _send_charging_completion(self):
        """发送充电完成通知"""
        if not self.current_session:
            return
            
        completion_message = {
            "type": "charging_completion",
            "message_id": str(uuid.uuid4()),
            "session_id": self.current_session["session_id"],
            "driver_id": self.current_session.get("driver_id"),
            "energy_consumed_kwh": round(self.charging_data["energy_consumed"], 3),
            "total_cost": round(self.charging_data["total_cost"], 2),
            "duration": self.current_session.get("duration", 0),
            "timestamp": int(time.time())
        }
        
        # 通过Monitor服务器发送给连接的Monitor客户端
        try:
            if self.monitor_server and hasattr(self.monitor_server, 'clients') and self.monitor_server.clients:
                for client_id in self.monitor_server.clients.keys():
                    self.monitor_server.send_message_to_client(client_id, completion_message)
                self.logger.info(f"Charging completion sent to Monitor: {completion_message}")
        except Exception as e:
            self.logger.error(f"Failed to send charging completion to Monitor: {e}")

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
            # 启动交互式命令处理线程
            command_thread = threading.Thread(target=self._interactive_commands, daemon=True)
            command_thread.start()
            
            while self.running:
                time.sleep(1)  # 保持运行

        except KeyboardInterrupt:
            self.logger.info("Shutting down EV_CP_E")
            self._shutdown_system()
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self._shutdown_system()

    def _interactive_commands(self):
        """交互式命令处理"""
        self.logger.info("Interactive commands available:")
        self.logger.info("  - Press 's' + Enter to start charging")
        self.logger.info("  - Press 'e' + Enter to end charging")
        self.logger.info("  - Press 'q' + Enter to quit")
        
        while self.running:
            try:
                command = input().strip().lower()
                
                if command == 'q':
                    self.logger.info("Quit command received")
                    self.running = False
                    break
                elif command == 's':
                    #if not self.is_charging:
                    #    self._start_charging_session("manual_ev")
                    #    self.logger.info("Manual charging started")
                    #else:
                    #    self.logger.info("Already charging")
                    if self.is_charging:
                        self.logger.warning("Already charging, cannot start new session")
                        self.logger.warning("Use 'e' to end current charging session first")

                        if self.current_session:
                            self.logger.info(f"Current session ID: {self.current_session['session_id']}")
                            self.logger.info(f"Driver: {self.current_session.get('driver_id', 'unknown_driver')}")
                    else:
                        # solo permitir inicio manual si no hay sesión activa
                        self._start_charging_session("manual_ev","manual_driver")
                        self.logger.info("Manual charging started")

                elif command == 'e':
                    if self.is_charging:
                        if self.current_session:
                            ev_id = self.current_session.get("ev_id", "manual_ev")
                            self._stop_charging_session(ev_id)
                            self.logger.info("Manual charging stopped")
                        else:
                            self.logger.warning("No current session found")
                        #self._stop_charging_session("manual_ev")
                        #self.logger.info("Manual charging stopped")
                    else:
                        self.logger.info("No active charging session")
                else:
                    self.logger.info("Unknown command. Use 's' to start, 'e' to end, 'q' to quit")
                    
            except EOFError:
                # 处理输入结束
                break
            except Exception as e:
                self.logger.error(f"Error in interactive commands: {e}")
                break


if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    ev_cp_e = EV_CP_E(logger=logger)
    ev_cp_e.start()
