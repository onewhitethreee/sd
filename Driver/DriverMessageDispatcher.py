import time
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Common.Message.MessageTypes import MessageTypes, ResponseStatus, MessageFields
from Common.Config.ConsolePrinter import get_printer


class DriverMessageDispatcher:

    def __init__(self, logger, driver):
        """
        Initializa el despachador de mensajes del Driver

        Args:
            logger: Custom logger para el Driver
            driver: Instancia del Driver
        """
        self.logger = logger
        self.driver = driver
        self.printer = get_printer()  # 使用美化输出工具

        # Mensaje viene de kafka Consumer en EV_Driver
        self.handlers = {
            # Respuestas
            MessageTypes.CHARGE_REQUEST_RESPONSE: self._handle_charge_response,
            MessageTypes.STOP_CHARGING_RESPONSE: self._handle_stop_charging_response,
            MessageTypes.AVAILABLE_CPS_RESPONSE: self._handle_available_cps,
            MessageTypes.CHARGING_HISTORY_RESPONSE: self._handle_charging_history_response,
            # Notificaciones
            MessageTypes.CHARGING_STATUS_UPDATE: self._handle_charging_status,
            MessageTypes.CHARGING_DATA: self._handle_charging_data,
            MessageTypes.CHARGE_COMPLETION: self._handle_charge_completion,
            # Eventos del sistema
            MessageTypes.CONNECTION_LOST: self._handle_connection_lost,
            MessageTypes.CONNECTION_ERROR: self._handle_connection_error,
        }

    def dispatch_message(self, message):
        """
        Despacha el mensaje entrante al manejador correspondiente

        Args:
            message: Diccionario del mensaje

        Returns:
            bool: Indica si el procesamiento fue exitoso
        """
        try:
            msg_type = message.get(MessageFields.TYPE)
            self.logger.debug(f"Dispatching message type: {msg_type}")

            handler = self.handlers.get(msg_type)
            if handler:
                return handler(message)
            else:
                self.logger.warning(
                    f"Unknown message type from Central: {msg_type}. "
                    f"Message ID: {message.get(MessageFields.MESSAGE_ID)}"
                )
                return False

        except Exception as e:
            self.logger.error(
                f"Error dispatching message {message.get(MessageFields.TYPE)}: {e}. "
                f"Message: {message}",
                exc_info=True,
            )
            return False

    def _handle_charge_response(self, message):
        """
        maneja la respuesta a la solicitud de carga

        Args:
            message: Mensaje de respuesta, que contiene:
                - status: "success" o "failure"
                - message/info: Descripción de la respuesta
                - session_id: ID de sesión (en caso de éxito)
                - cp_id: ID de punto de carga (en caso de éxito)
        """
        status = message.get(MessageFields.STATUS)
        info = message.get("info", message.get(MessageFields.MESSAGE, ""))
        self.logger.debug(f"Charge response message: {message}")

        if status == ResponseStatus.SUCCESS:
            self.logger.info(f"✓  charging requests approved: {info}")
            session_id = message.get(MessageFields.SESSION_ID)
            cp_id = message.get(MessageFields.CP_ID)

            if session_id:
                with self.driver.lock:
                    self.driver.current_charging_session = {
                        "session_id": session_id,
                        "cp_id": cp_id,
                        "start_time": time.time(),
                        "status": "authorized",
                        "energy_consumed_kwh": 0.0,
                        "total_cost": 0.0,
                    }
                self.logger.info(f"✓  Charging session created: {session_id}")
                self.logger.debug(f"Session data: {self.driver.current_charging_session}")
            else:
                self.logger.error("Session ID not provided in charge response")
        else:
            self.logger.error(f"✗  Charging request denied: {info}")

        return True

    def _handle_charging_status(self, message):
        """
        maneja la actualización de estado de carga

        Args:
            message: Mensaje de actualización de estado, que contiene:
                - session_id: ID de sesión
                - energy_consumed_kwh: Energía consumida
                - total_cost: Costo total
                - status: Estado (opcional, "error" indica fallo del CP)
                - reason: Razón del error (opcional)
                - message: Mensaje descriptivo (opcional)
        """
        session_id = message.get(MessageFields.SESSION_ID)
        energy_consumed_kwh = message.get(MessageFields.ENERGY_CONSUMED_KWH, 0)
        total_cost = message.get(MessageFields.TOTAL_COST, 0)
        status = message.get(MessageFields.STATUS)
        reason = message.get(MessageFields.REASON)
        error_message = message.get(MessageFields.MESSAGE)

        # Si el mensaje indica un error (fallo del CP)
        if status == "error":
            cp_id = message.get(MessageFields.CP_ID, "Unknown CP")
            self.logger.error(f"⚠️  CHARGING POINT FAULT DETECTED!")
            self.logger.error(f"CP: {cp_id}, Session: {session_id}")
            self.logger.error(f"Reason: {reason}")
            if error_message:
                self.logger.error(f"Message: {error_message}")
            self.logger.warning(f"Energy consumed before fault: {energy_consumed_kwh:.3f} kWh")
            self.logger.warning(f"Cost before fault: €{total_cost:.2f}")
            self.logger.info("Session has been suspended. Data will be sent when CP recovers.")
            return True

        with self.driver.lock:
            if self.driver.current_charging_session:
                current_session_id = self.driver.current_charging_session.get(
                    "session_id"
                )
                if current_session_id == session_id:
                    self.driver.current_charging_session["energy_consumed_kwh"] = (
                        energy_consumed_kwh
                    )
                    self.driver.current_charging_session["total_cost"] = total_cost

                    self.logger.debug(
                        f"🔋 Charging progress - Energy: {energy_consumed_kwh:.3f}kWh, Cost: €{total_cost:.2f}"
                    )
                else:
                    self.logger.warning(
                        f"ID de sesión no coincide: se esperaba {current_session_id}, se recibió {session_id}"
                    )
            else:
                # self.logger.warning(
                #     f"No hay sesiones de carga activas, no se puede actualizar el estado. ID de sesión recibido: {session_id}"
                # )
                pass

        return True

    def _handle_charging_data(self, message):
        """
        maneja los datos de carga en tiempo real. Origen viene de kafka Consumer

        Args:
            message: Mensaje de datos de carga, que contiene:
                - session_id: ID de sesión
                - energy_consumed_kwh: Energía consumida
                - total_cost: Costo total
        """
        session_id = message.get(MessageFields.SESSION_ID)
        with self.driver.lock:
            if (
                self.driver.current_charging_session
                and self.driver.current_charging_session.get("session_id") == session_id
            ):
                energy_consumed_kwh = message.get(MessageFields.ENERGY_CONSUMED_KWH, 0)
                total_cost = message.get(MessageFields.TOTAL_COST, 0)

                self.driver.current_charging_session["energy_consumed_kwh"] = (
                    energy_consumed_kwh
                )
                self.driver.current_charging_session["total_cost"] = total_cost

                self.logger.debug(
                    f"🔋 Real-time charging data - Energy: {energy_consumed_kwh:.3f}kWh, Cost: €{total_cost:.2f}"
                )

        return True

    def _handle_charge_completion(self, message):
        """
        maneja la notificación de finalización de carga

        Args:
            message: Mensaje de notificación de finalización, que contiene:
                - session_id: ID de sesión
                - energy_consumed_kwh: Energía consumida total
                - total_cost: Costo total
        """
        session_id = message.get(MessageFields.SESSION_ID)
        energy_consumed_kwh = message.get(MessageFields.ENERGY_CONSUMED_KWH, 0)
        total_cost = message.get(MessageFields.TOTAL_COST, 0)
        cp_id = message.get(MessageFields.CP_ID, "N/A")
        
        with self.driver.lock:
            # 检查是否有匹配的当前会话
            if self.driver.current_charging_session:
                current_session_id = self.driver.current_charging_session.get("session_id")
                
                # 如果session_id匹配，使用当前会话的信息
                if current_session_id == session_id:
                    current_session = self.driver.current_charging_session
                    cp_id = current_session.get("cp_id", cp_id)
                    driver_id = self.driver.args.id_client if hasattr(self.driver.args, 'id_client') else "N/A"
                    start_time = current_session.get("start_time")
                    
                    # 构建完整的会话数据用于ticket
                    ticket_data = {
                        "session_id": session_id,
                        "cp_id": cp_id,
                        "driver_id": driver_id,
                        "energy_consumed_kwh": energy_consumed_kwh,
                        "total_cost": total_cost,
                        "start_time": start_time,
                        "end_time": time.time(),  # 当前时间作为结束时间
                    }
                    
                    # 使用Rich美化显示充电完成票据
                    self.printer.print_charging_ticket(ticket_data)
                    
                    # 重要：清除当前充电会话，标记为已完成
                    self.driver.current_charging_session = None
                    
                    self.logger.info(f"✓  Charging session {session_id} completed successfully")
                else:
                    # Session ID不匹配，可能是重连后的延迟消息
                    self.logger.warning(
                        f"Received charge_completion for session {session_id}, "
                        f"but current session is {current_session_id}. "
                        f"This may be a delayed message after reconnection."
                    )
                    # 仍然显示完成信息
                    self.printer.print_success(f"Charging session {session_id} completed")
                    self.printer.print_key_value("Energy consumed", f"{energy_consumed_kwh:.3f} kWh")
                    self.printer.print_key_value("Total cost", f"€{total_cost:.2f}")
                    
                    # 如果当前会话ID不匹配，清除当前会话（可能是旧会话）
                    self.driver.current_charging_session = None
            else:
                # 没有当前会话，可能是重连后的延迟消息
                self.logger.info(
                    f"Received charge_completion for session {session_id} "
                    f"but no active session found. This may be a delayed message after reconnection."
                )
                self.printer.print_success(f"Charging session {session_id} completed")
                self.printer.print_key_value("Energy consumed", f"{energy_consumed_kwh:.3f} kWh")
                self.printer.print_key_value("Total cost", f"€{total_cost:.2f}")

        # 只有在有service_queue时才处理下一个服务
        # 如果没有service_queue，说明是手动模式，不需要自动处理下一个服务
        if hasattr(self.driver, 'service_queue') and self.driver.service_queue:
            self.logger.info("Waiting 4 seconds before next service...")
            time.sleep(4)
            self.driver._process_next_service()

        return True

    def _handle_available_cps(self, message):
        """
        Maneja la respuesta de puntos de carga disponibles

        Args:
            message: Mensaje de lista, que contiene:
                - charging_points: Lista de puntos de carga disponibles
        """
        self.driver.available_charging_points = message.get(
            MessageFields.CHARGING_POINTS, []
        )
        self.driver.available_cps_cache_time = time.time()  # Actualizar tiempo de caché

        self.logger.debug(
            f"Available charging points: {len(self.driver.available_charging_points)}"
        )

        return True

    def _handle_charging_history_response(self, message):
        """
        Maneja la respuesta de historial de carga

        Args:
            message: Mensaje de respuesta de historial, que contiene:
                - status: Estado de la respuesta
                - history: Lista de historial de carga
                - count: Número de registros
        """
        status = message.get(MessageFields.STATUS)

        if status == "success":
            history = message.get("history", [])
            count = message.get("count", 0)

            self.printer.print_success(f"Received {count} charging history records from Central")

            self.driver._show_charging_history(history)
        else:
            error = message.get("error", "Unknown error")
            self.printer.print_error(f"Failed to retrieve charging history: {error}")

        return True

    def _handle_connection_lost(self, message):
        """
        Maneja la pérdida de conexión

        Args:
            message: Mensaje de notificación de pérdida de conexión
        """
        self.logger.warning(f"Connection to Central lost: {message}")
        self.driver._handle_connection_lost()
        return True

    def _handle_connection_error(self, message):
        """
        Maneja los errores de conexión
        Args:
            message: Mensaje de notificación de error de conexión
        """
        error = message.get("error", "Unknown error")
        # self.logger.error(f"Connection error: {error}")
        self.driver._handle_connection_error(message)
        return True

    def _handle_stop_charging_response(self, message):
        """
        Maneja la respuesta de detención de carga

        Args:
            message: Mensaje de respuesta, que contiene:
                - status: Estado de la respuesta (success/failure)
                - message/info: Información de la respuesta
                - session_id: ID de sesión
                - cp_id: ID de punto de carga

        Returns:
            bool: Indica si el procesamiento fue exitoso
        """
        status = message.get(MessageFields.STATUS)
        info = message.get("info", message.get(MessageFields.MESSAGE, ""))
        session_id = message.get(MessageFields.SESSION_ID)
        cp_id = message.get(MessageFields.CP_ID)

        self.logger.debug(f"Processing stop charging response: status={status}, info={info}")

        if status == ResponseStatus.SUCCESS:
            self.logger.info(
                f"🛑 Stop charging request accepted for session {session_id}"
            )
            self.logger.info(f"   Charging point: {cp_id}")
            self.logger.info(f"   Waiting for final charge completion notification...")

        else:
            self.logger.error(f"✗  Failed to stop charging: {info}")
            self.logger.error(f"   Session ID: {session_id}")

            with self.driver.lock:
                if self.driver.current_charging_session:
                    local_session_id = self.driver.current_charging_session.get(
                        "session_id"
                    )
                    if local_session_id != session_id:
                        self.logger.warning(
                            f"   Local session ID ({local_session_id}) differs from requested ({session_id})"
                        )

        return True
