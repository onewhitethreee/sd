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

        self.remaining_charges = 0           # Contador de cargas pendientes
        self.preferred_cp_queue = []         # CPs preferidos del archivo
        self.waiting_for_cps_list = False    # Flag para esperar respuesta de CPs disponibles
        
    def _connect_to_central(self):
        """Conectarse al sistema central"""
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
        """Manejar mensajes recibidos del sistema central"""
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
        """Manejar la respuesta a la solicitud de carga"""
        status = message.get("status")
        info = message.get("info", "")
        
        if status == "success":         # Punto de recarga APROBADO
            self.logger.info(f"Charging request approved: {info}")
            session_id = message.get("session_id")
            cp_id = message.get("cp_id")

            if session_id:
                self.current_charging_session = {
                    "session_id": session_id,
                    "cp_id": cp_id,
                    "start_time": datetime.now(),
                    "status": "authorized"
                }
                self.logger.info(f"Charging session started: {session_id}")

                if cp_id:
                    self.logger.info(f"Using charging point: {cp_id}")
        else:                           # Punto de recarga DENEGADO 
            self.logger.warning(f"Charging request denied: {info}")
            self.logger.info("Looking for alternative charging points...")

            # Solicitar la lista de puntos de recarga disponibles
            self.waiting_for_cps_list = True
            self._request_available_cps()

            # Esperar respuesta --> la lógica continúa en _handle_available_cps
    
    def _handle_charging_status(self, message):
        """Manejar actualizaciones de estado de carga"""
        if self.current_charging_session:
            energy_consumed = message.get("energy_consumed_kwh", 0)
            total_cost = message.get("total_cost", 0)
            self.logger.info(f"Charging progress - Energy: {energy_consumed}kWh, Cost: €{total_cost}")
    
    def _handle_charge_completion(self, message):
        """Manejar la notificación de finalización de carga"""
        if self.current_charging_session:
            session_id = message.get("session_id")
            energy_consumed = message.get("energy_consumed_kwh", 0)
            total_cost = message.get("total_cost", 0)
            
            self.logger.info(f"Charging completed!")
            self.logger.info(f"Session ID: {session_id}")
            self.logger.info(f"Total Energy: {energy_consumed}kWh")
            self.logger.info(f"Total Cost: €{total_cost}")
            
            self.current_charging_session = None

            # Decrementar contador de cargas pendientes
            self.remaining_charges -= 1
            if self.remaining_charges > 0:
                # Esperar 4 segundos antes de siguiente servicio
                self.logger.info(f"Waiting 4 seconds before next service... ({self.remaining_charges} remaining)")
                time.sleep(4)
                self._process_next_service()
            else:
                self.logger.info("All requested charging services completed.")
    
    def _handle_available_cps(self, message):
        """Manejar la respuesta de puntos de recarga disponibles"""
        self.available_charging_points = message.get("charging_points", [])
        self.logger.info(f"Available charging points: {len(self.available_charging_points)}")
        
        for cp in self.available_charging_points:
            self.logger.info(f"  - {cp['id']}: {cp['location']} (Status: {cp['status']})")

        # Si está esperando alternativas, intentar solicitar carga en el primer punto disponible
        if self.waiting_for_cps_list:
            self.waiting_for_cps_list = False
            self._try_alternative_charging_point()

    def _try_alternative_charging_point(self):
        """Intentar solicitar un punto de recarga alternativo"""
        active_cps = [cp for cp in self.available_charging_points if cp.get('status') == 'ACTIVE'] 
        
        self.logger.debug(f"Active CPs found: {len(active_cps)}")
        for cp in active_cps:
            self.logger.debug(f"  - {cp['id']} is ACTIVE") 

        if not active_cps:
            self.logger.error("No alternative charging points available.")
            self.logger.warning("Chargin request failed - no available CPs.")

            self.remaining_charges -= 1

            if self.remaining_charges > 0:
                self.logger.info(f"Waiting 4 seconds before next service... ({self.remaining_charges} remaining)")
                time.sleep(4)
                self._process_next_service()
            else:
                self.logger.info("All requested charging services completed.")
            
            return

        #Seleccionar el primer punto de recarga disponible
        alternative_cp = active_cps[0]

        self.logger.info(f"Alternative charging point found: {alternative_cp['id']}")
        self.logger.info(f"Location: {alternative_cp['location']}")
        self.logger.info(f"Precio por kWh: €{alternative_cp['price_per_kwh']}")

        #Solicitar carga en el punto alternativo
        self._send_charge_request(alternative_cp['id'])
    
    def _send_charge_request(self, cp_id):
        """Enviar solicitud de carga para un punto de recarga específico"""
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
        """Solicitar la lista de puntos de recarga disponibles"""
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
        """Cargar servicios de puntos de recarga peferidos de los Drivers desde un archivo"""
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
        """Procesar el siguiente servicio de manera inteligente"""
        if self.remaining_charges <= 0:
            self.logger.info("All charging requests completed")
            return
        
        # Obtener CP preferido si hay está en la cola
        preferred_cp = None
        if self.preferred_cp_queue:
            preferred_cp = self.preferred_cp_queue.pop(0)
        
        if preferred_cp:
            self.logger.info(f"Processing service {len(self.preferred_cp_queue) + 1}/{self.remaining_charges + len(self.preferred_cp_queue)}")
            self.logger.info(f"Preferred CP: {preferred_cp}")
            
            # Intentar con CP preferido
            self._send_charge_request(preferred_cp)
        else:
            # No hay CP preferido, buscar cualquier disponible
            self.logger.info(f"No preferred CP, looking for any available... ({self.remaining_charges} remaining)")
            self.waiting_for_cps_list = True
            self._request_available_cps()
    
    def _interactive_mode(self):
        """Modo interactivo"""
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
        """Modo automático"""
        self.logger.info(f"Entering auto mode with {len(services)} charging requests")
        
        # Guardar CPs preferidos y contador
        self.preferred_cp_queue = services.copy()
        self.remaining_charges = len(services)
        
        self.logger.info(f"Will attempt charging at {self.remaining_charges} charging points")
        
        # Iniciar primer servicio
        if self.remaining_charges > 0:
            self._process_next_service()
        
        # Esperar a que terminen todos los servicios
        while self.running and (self.remaining_charges > 0 or self.current_charging_session):
            time.sleep(1)
    
    def start(self):
        """Iniciar Driver"""
        self.logger.info(f"Starting Driver module")
        central_address = self.config.get_ip_port_ev_cp_central()
        self.logger.info(f"Connecting to Central at {central_address[0]}:{central_address[1]}")
        self.logger.info(f"Client ID: {self.args.id_client}")
        
        # Conenctar al Central
        if not self._connect_to_central():
            self.logger.error("Failed to connect to Central")
            return
        
        self.running = True
        
        # Solicitar puntos de recargas disponibles
        self._request_available_cps()
        time.sleep(2)
        
        # Verificar si hay archivo de servicios
        services = self._load_services_from_file()
        
        try:
            if services:
                # Modo automático
                self._auto_mode(services)
            else:
                # Modo interactivo
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