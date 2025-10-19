"""
Aplicación que usan los consumidores para usar los puntos de recarga
"""

import sys
import os
import time
import uuid
import json
import threading
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from Common.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.CustomLogger import CustomLogger
from Common.ConfigManager import ConfigManager
from Common.MySocketClient import MySocketClient

class Driver:
    def __init__(self, logger=None):
        self.logger = logger
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()
        
        if not self.debug_mode:
            self.tools = AppArgumentParser("Driver", "Aplicación del conductor para usar puntos de recarga")            
            self.tools.add_argument("broker", type=ip_port_type, help="IP y puerto del Broker/Bootstrap-server del gestor de colas (formato IP:PORT)")
            self.tools.add_argument("id_client", type=str, help="Identificador único del cliente")
            self.args = self.tools.parse_args()
        else:
            class Args:
                broker = self.config.get_broker()
                id_client = self.config.get_client_id()
            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")
        
        self.central_client = None
        self.running = False
        self.current_charging_session = None
        self.available_charging_points = []
        self.service_queue = []
        
    def _connect_to_central(self):
        """连接到中央系统"""
        try:
            central_address = self.config.get_ip_port_ev_cp_central()    # obtener la dirección del central desde la configuración

            self.central_client = MySocketClient(
                logger=self.logger,
                message_callback=self._handle_central_message,
            )
            #return self.central_client.connect(self.args.broker[0], self.args.broker[1])  # Conecta al broker, en vez de al central directamente
            success = self.central_client.connect(central_address[0], central_address[1])   # Conecta al central, NO al broker

            if success:
                self.logger.info(f"Connected to Central at {central_address[0]}:{central_address[1]}")
            
            return success                                 
        except Exception as e:
            self.logger.error(f"Failed to connect to Central: {e}")
            return False
    
    def _handle_central_message(self, message):
        """处理来自中央系统的消息"""
        message_type = message.get("type")
        
        if message_type == "charge_request_response":
            self._handle_charge_response(message)
        elif message_type == "charging_status_update":
            self._handle_charging_status(message)
        elif message_type == "charge_completion_notification":
            self._handle_charge_completion(message)
        elif message_type == "available_cps_response":
            self._handle_available_cps(message)
        else:
            self.logger.warning(f"Unknown message type from Central: {message_type}")
    
    def _handle_charge_response(self, message):
        """处理充电请求响应"""
        status = message.get("status")
        info = message.get("info", "")
        
        if status == "success":
            self.logger.info(f"✅ Charging request approved: {info}")
            session_id = message.get("session_id")
            if session_id:
                self.current_charging_session = {
                    "session_id": session_id,
                    "cp_id": message.get("cp_id"),
                    "start_time": datetime.now(),
                    "status": "authorized"
                }
                self.logger.info(f"Charging session started: {session_id}")
        else:
            self.logger.error(f"❌ Charging request denied: {info}")
    
    def _handle_charging_status(self, message):
        """处理充电状态更新"""
        if self.current_charging_session:
            energy_consumed = message.get("energy_consumed_kwh", 0)
            total_cost = message.get("total_cost", 0)
            self.logger.info(f"🔋 Charging progress - Energy: {energy_consumed}kWh, Cost: €{total_cost}")
    
    def _handle_charge_completion(self, message):
        """处理充电完成通知"""
        if self.current_charging_session:
            session_id = message.get("session_id")
            energy_consumed = message.get("energy_consumed_kwh", 0)
            total_cost = message.get("total_cost", 0)
            
            self.logger.info(f"✅ Charging completed!")
            self.logger.info(f"Session ID: {session_id}")
            self.logger.info(f"Total Energy: {energy_consumed}kWh")
            self.logger.info(f"Total Cost: €{total_cost}")
            
            self.current_charging_session = None
            
            # 等待4秒后处理下一个服务
            self.logger.info("Waiting 4 seconds before next service...")
            time.sleep(4)
            self._process_next_service()
    
    def _handle_available_cps(self, message):
        """处理可用充电点列表"""
        self.available_charging_points = message.get("charging_points", [])
        self.logger.info(f"Available charging points: {len(self.available_charging_points)}")
        for cp in self.available_charging_points:
            self.logger.info(f"  - {cp['id']}: {cp['location']} (Status: {cp['status']})")
    
    def _send_charge_request(self, cp_id):
        """发送充电请求"""
        if not self.central_client or not self.central_client.is_connected:
            self.logger.error("Not connected to Central")
            return False
        
        request_message = {
            "type": "charge_request",
            "message_id": str(uuid.uuid4()),
            "cp_id": cp_id,
            "driver_id": self.args.id_client,
            "timestamp": int(time.time())
        }
        
        self.logger.info(f"🚗 Sending charging request for CP: {cp_id}")
        return self.central_client.send(request_message)
    
    def _request_available_cps(self):
        """请求可用充电点列表"""
        if not self.central_client or not self.central_client.is_connected:
            self.logger.error("Not connected to Central")
            return False
        
        request_message = {
            "type": "available_cps_request",
            "message_id": str(uuid.uuid4()),
            "driver_id": self.args.id_client,
            "timestamp": int(time.time())
        }
        
        return self.central_client.send(request_message)
    
    def _load_services_from_file(self, filename="test_services.txt"):
        """从文件加载服务列表"""
        try:
            if not os.path.exists(filename):
                self.logger.warning(f"Service file {filename} not found")
                return []
            
            with open(filename, 'r') as f:
                services = [line.strip() for line in f if line.strip()]
            
            self.logger.info(f"Loaded {len(services)} services from {filename}")
            return services
        except Exception as e:
            self.logger.error(f"Error loading services from file: {e}")
            return []
    
    def _process_next_service(self):
        """处理下一个服务"""
        if self.service_queue:
            cp_id = self.service_queue.pop(0)
            self.logger.info(f"Processing next service: {cp_id}")
            self._send_charge_request(cp_id)
        else:
            self.logger.info("No more services to process")
    
    def _interactive_mode(self):
        """交互模式"""
        self.logger.info("Entering interactive mode. Available commands:")
        self.logger.info("  - 'list': Show available charging points")
        self.logger.info("  - 'charge <cp_id>': Request charging at specific CP")
        self.logger.info("  - 'status': Show current charging status")
        self.logger.info("  - 'quit': Exit application")
        
        while self.running:
            try:
                command = input("\nDriver> ").strip().lower()
                
                if command == "quit":
                    self.running = False
                    break
                elif command == "list":
                    self._request_available_cps()
                elif command.startswith("charge "):
                    cp_id = command.split(" ", 1)[1]
                    self._send_charge_request(cp_id)
                elif command == "status":
                    if self.current_charging_session:
                        self.logger.info(f"Current session: {self.current_charging_session}")
                    else:
                        self.logger.info("No active charging session")
                else:
                    self.logger.info("Unknown command. Type 'quit' to exit.")
                    
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                self.logger.error(f"Error in interactive mode: {e}")
    
    def _auto_mode(self, services):
        """自动模式"""
        self.logger.info(f"Entering auto mode with {len(services)} services")
        self.service_queue = services.copy()
        
        # 处理第一个服务
        if self.service_queue:
            self._process_next_service()
        
        # 等待所有服务完成
        while self.running and (self.service_queue or self.current_charging_session):
            time.sleep(1)
    
    def start(self):
        """启动Driver应用"""
        self.logger.info(f"Starting Driver module")
        #self.logger.info(f"Connecting to Broker at {self.args.broker[0]}:{self.args.broker[1]}")
        central_address = self.config.get_ip_port_ev_cp_central()
        self.logger.info(f"Connecting to Central at {central_address[0]}:{central_address[1]}")
        self.logger.info(f"Client ID: {self.args.id_client}")
        
        # 连接到中央系统
        if not self._connect_to_central():
            self.logger.error("Failed to connect to Central")
            return
        
        self.running = True
        
        # 请求可用充电点列表
        self._request_available_cps()
        time.sleep(2)
        
        # 检查是否有服务文件
        services = self._load_services_from_file()
        
        try:
            if services:
                # 自动模式
                self._auto_mode(services)
            else:
                # 交互模式
                self._interactive_mode()
                
        except KeyboardInterrupt:
            self.logger.info("Shutting down Driver")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
        finally:
            self.running = False
            if self.central_client:
                self.central_client.disconnect()

if __name__ == "__main__":
    logger = CustomLogger.get_logger()
    driver = Driver(logger=logger)
    driver.start()

# TODO 需要有kafka的时候才能进行开发测试