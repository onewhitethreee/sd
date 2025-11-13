"""
Módulo que monitoriza la salud de todo el punto de recarga y que reporta a la CENTRAL cualquier avería de este. Sirve igualmente para autenticar y registrar a los CP en la central cuando sea oportuno.
"""

import sys
import os
import uuid
import time
import threading
import random


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Config.AppArgumentParser import AppArgumentParser, ip_port_type
from Common.Config.CustomLogger import CustomLogger
from Common.Config.ConfigManager import ConfigManager
from Charging_point.Monitor.ConnectionManager import ConnectionManager
from Common.Config.Status import Status
from Charging_point.Monitor.MonitorMessageDispatcher import MonitorMessageDispatcher
from Common.Message.MessageTypes import MessageFields, MessageTypes


class EV_CP_M:
    def __init__(self, logger=None, enable_panel=True):
        self.logger = logger
        self.config = ConfigManager()
        self.debug_mode = self.config.get_debug_mode()

        if not self.debug_mode:
            self.tools = AppArgumentParser(
                "EV_CP_M", "Módulo de monitorización del punto de recarga"
            )
            self.tools.add_argument(
                "ip_port_ev_cp_e",
                type=ip_port_type,
                help="IP y puerto del EV_CP_E (formato IP:PORT)",
            )
            self.tools.add_argument(
                "ip_port_ev_central",
                type=ip_port_type,
                help="IP y puerto del EV_CP_Central (formato IP:PORT)",
            )
            self.tools.add_argument(
                "id_cp", type=str, help="Identificador único del punto de recarga"
            )
            self.args = self.tools.parse_args()
            enable_panel = False
        else:

            class Args:
                ip_port_ev_cp_e = self.config.get_ip_port_ev_cp_e()
                ip_port_ev_central = self.config.get_ip_port_ev_cp_central()
                id_cp = f"cp_{random.randint(0,99999)}"
                no_panel = not enable_panel

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        self.central_conn_mgr: ConnectionManager = None  # ConnectionManager 实例
        self.engine_conn_mgr: ConnectionManager = None  # ConnectionManager 实例
        self.running = False

        self._current_status = Status.DISCONNECTED.value  # 当前充电点状态

        self._heartbeat_thread = None
        self._engine_health_thread = None

        # 状态面板 - 可以通过CLI控制
        self.enable_panel = True  # 始终允许启用面板（通过CLI）
        self.status_panel = None
        self._auto_start_panel = enable_panel  # 是否自动启动面板

        # CLI控制 - 默认启用
        self.cli = None

        self.HEARTBEAT_INTERVAL = 30  # 向 Central 发送心跳的间隔（秒）
        self.ENGINE_HEALTH_TIMEOUT = (
            90  # 如果超过这个时间没有收到 Engine 的健康响应，则认为故障（秒）
        )
        self.ENGINE_HEALTH_CHECK_INTERVAL = 30  # 向 Engine 发送健康

        # 用于追踪最后一次收到Engine健康检查响应的时间
        self._last_health_response_time = None

        # 注册确认标志（修复竞态条件）
        self._registration_confirmed = False

        # 认证标志：是否已通过认证
        self._authorized = False

        # 当前充电会话数据（用于状态面板显示）
        self._current_charging_data = None  # {session_id, driver_id, energy_consumed_kwh, total_cost, start_time}

        # 消息队列：当Central断开时，堆积需要发送给Central的消息
        self._pending_messages_to_central = []  # 队列，存储待发送的消息
        self._pending_messages_lock = threading.Lock()  # 保护消息队列的锁

        # 初始化消息分发器
        self.message_dispatcher = MonitorMessageDispatcher(self.logger, self)

    def _register_with_central(self):
        """
        和central注册一个charging point (现在由 ConnectionManager 发送)。

        注意：必须先通过认证才能注册。
        """
        if not self.central_conn_mgr.is_connected:
            self.logger.warning("Not connected to Central, can't register.")
            return False
        if not self.engine_conn_mgr.is_connected:
            self.logger.warning("Not connected to Engine, can't register.")
            return False

        # 检查是否已通过认证
        if not self._authorized:
            self.logger.warning(
                "Not authorized yet, cannot register. Please authenticate first."
            )
            return False

        # 重置注册确认标志，等待 Central 响应
        self._registration_confirmed = False

        register_message = {
            "type": "register_request",
            "message_id": str(uuid.uuid4()),
            "id": self.args.id_cp,
            "location": "Unknown",
            "price_per_kwh": 0.20,
        }
        success = self.central_conn_mgr.send(register_message)
        if success:
            self.logger.debug(
                "Registration request sent to Central, waiting for confirmation..."
            )
        return success

    def _handle_connection_status_change(self, source_name: str, status: str):
        """
        由 ConnectionManager 回调，处理连接状态变化。
        这就是 EV_CP_M 响应底层网络事件的核心逻辑。

        """
        self.logger.debug(f"Connection status for {source_name} changed to {status}")
        if source_name == "Central":
            if status == "CONNECTED":
                self.logger.debug(
                    "Central is now connected. Attempting to authenticate..."
                )
                # 先发送认证请求，只有认证成功后才能注册
                if not self._authorized:
                    self.authenticate_charging_point()
                else:
                    # 如果已经授权，直接尝试注册
                    self._register_with_central()
                # 启动 Central 的心跳线程
                self._start_heartbeat_thread()
                # Solo establecer ACTIVE si Engine también está conectado y funcionando
                # De lo contrario, esperar a que Engine confirme su estado
                if self.engine_conn_mgr and self.engine_conn_mgr.is_connected:
                    self._check_and_update_to_active()
                else:
                    self.logger.info(
                        "Waiting for Engine connection before setting ACTIVE status"
                    )
            elif status == "DISCONNECTED":
                self.logger.warning(
                    "Central is disconnected. Handling disconnection..."
                )
                # 处理Central断开连接的情况
                self._handle_central_disconnection()
                self._stop_heartbeat_thread()  # 停止心跳
            else:
                self.logger.warning(f"Unknown status '{status}' for Central")
        elif source_name == "Engine":
            if status == "CONNECTED":
                self.logger.debug("Engine is now connected. Initializing CP_ID...")
                self._send_cp_id_to_engine()

                # 然后启动健康检查线程
                self._start_engine_health_check_thread()
                # Si Central también está conectado, actualizar a ACTIVE
                if self.central_conn_mgr and self.central_conn_mgr.is_connected:
                    self._check_and_update_to_active()
                else:
                    self.logger.info(
                        "Waiting for Central connection before setting ACTIVE status"
                    )
            elif status == "DISCONNECTED":
                self.logger.warning("Engine is disconnected. Reporting failure.")
                self._report_failure("EV_CP_E connection lost")
                # 检查当前状态，如果是 STOPPED，不应该改为 FAULTY
                if self._current_status == Status.STOPPED.value:
                    self.logger.warning(
                        "CP is STOPPED by admin, ignoring Engine disconnection (not changing to FAULTY)"
                    )
                else:
                    # Monitor OK pero Engine KO => FAULTY
                    self.update_cp_status(Status.FAULTY.value)
                self._stop_engine_health_check_thread()  # 停止健康检查

    def _handle_central_disconnection(self):
        """
        处理Central断开连接的情况

        当Central断开时：
        1. 如果正在充电，继续完成charging（不要停止）
        2. 堆积charge_completion消息，等待Central恢复后发送
        3. 拒绝新的charge请求，直到Central恢复连接
        4. 更新充电点状态为FAULTY
        5. ConnectionManager会自动尝试重连
        """
        self.logger.warning("Handling Central disconnection...")

        # 检查当前状态，如果是 STOPPED，不应该改为 FAULTY
        if self._current_status == Status.STOPPED.value:
            self.logger.warning(
                "CP is STOPPED by admin, ignoring Central disconnection (not changing to FAULTY)"
            )
            return

        # 重要：如果正在充电，不要停止charging
        # 继续完成charging，消息会堆积在队列中，等待Central恢复后发送
        if self._current_status == Status.CHARGING.value:
            self.logger.warning(
                "Currently charging, but Central is disconnected. "
                "Charging will continue, and completion messages will be queued until Central reconnects."
            )

        # 更新状态为FAULTY（失去与Central的连接）
        # 注意：如果正在充电，状态仍然是CHARGING，但标记为FAULTY表示无法与Central通信
        # 实际上，我们需要一个更细粒度的状态管理，但为了简化，我们保持CHARGING状态
        # 只有在非CHARGING状态下才更新为FAULTY
        if self._current_status != Status.CHARGING.value:
            self.update_cp_status(Status.FAULTY.value)
            self.logger.info(
                "CP status set to FAULTY due to Central disconnection. Waiting for reconnection..."
            )
        else:
            self.logger.info(
                "CP is CHARGING, status remains CHARGING. "
                "Will queue completion messages until Central reconnects."
            )

    def _check_and_update_to_active(self):
        """
        检查是否满足ACTIVE状态的条件，并更新状态
        只有当Central和Engine都连接成功，且注册已确认时才更新为ACTIVE
        """
        if (
            self._registration_confirmed
            and self.central_conn_mgr
            and self.central_conn_mgr.is_connected
            and self.engine_conn_mgr
            and self.engine_conn_mgr.is_connected
        ):
            # 检查当前状态，如果是STOPPED，不能自动改为ACTIVE
            # STOPPED状态只能由Central的resume命令来改变
            if self._current_status == Status.STOPPED.value:
                self.logger.debug(
                    "CP is STOPPED by admin, cannot auto-update to ACTIVE (health check ignored)"
                )
                return

            # 只有在当前状态不是ACTIVE时才更新
            if self._current_status != Status.ACTIVE.value:
                self.logger.debug(
                    "Central registered, both Central and Engine connected, setting CP status to ACTIVE"
                )
                self.update_cp_status(Status.ACTIVE.value)
            else:
                self.logger.debug("CP status is already ACTIVE, no update needed")
        else:
            self.logger.debug(
                f"Not ready for ACTIVE status: Registered={self._registration_confirmed}, "
                f"Central={self.central_conn_mgr.is_connected if self.central_conn_mgr else False}, "
                f"Engine={self.engine_conn_mgr.is_connected if self.engine_conn_mgr else False}"
            )

    def _stop_engine_health_check_thread(self):
        """停止对 Engine 的健康检查线程"""
        if self._engine_health_thread and self._engine_health_thread.is_alive():
            self.logger.debug("Stopping Engine health check thread.")
            # 通过设置 running 标志让线程自然退出
            # 这里假设线程会检查 self.running 和 conn_mgr.is_connected
            # 因为我们没有单独的停止事件，所以只能依赖这些条件
            # 实际上，线程会在下一次循环时检测到条件变化并退出
        else:
            self.logger.debug("Engine health check thread is not running.")

    def _stop_heartbeat_thread(self):
        """停止发送心跳的线程"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self.logger.debug("Stopping heartbeat thread for Central.")
            # 通过设置 running 标志让线程自然退出
            # 这里假设线程会检查 self.running 和 conn_mgr.is_connected
            # 因为我们没有单独的停止事件，所以只能依赖这些条件
            # 实际上，线程会在下一次循环时检测到条件变化并退出
        else:
            self.logger.debug("Heartbeat thread for Central is not running.")

    def _start_engine_health_check_thread(self):
        """启动对 Engine 的健康检查线程"""
        if self._engine_health_thread and self._engine_health_thread.is_alive():
            self.logger.debug("Engine health check thread already running.")
            return
        self.logger.debug("Starting Engine health check thread.")
        self._engine_health_thread = threading.Thread(
            target=self._check_engine_health,
            daemon=True,
            name="EngineHealthCheckThread",
        )
        self._engine_health_thread.start()

    def _send_heartbeat(self):
        """
        发送心跳消息以保持与central的连接。
        """
        while (
            self.running
            and self.central_conn_mgr
            and self.central_conn_mgr.is_connected
        ):
            heartbeat_msg = {
                "type": "heartbeat_request",
                "message_id": str(uuid.uuid4()),
                "id": self.args.id_cp,
            }
            if self.central_conn_mgr.send(heartbeat_msg):
                self.logger.debug("Heartbeat sent to Central.")
            else:
                self.logger.error(
                    "Failed to send heartbeat to Central (might be disconnected internally)."
                )
            time.sleep(self.HEARTBEAT_INTERVAL)
        self.logger.debug("Heartbeat thread for Central has stopped.")

    def _start_heartbeat_thread(self):
        """
        启动发送心跳的线程
        """
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self.logger.debug("Heartbeat thread for Central already running.")
            return
        self.logger.debug("Starting heartbeat thread for Central.")
        self._heartbeat_thread = threading.Thread(
            target=self._send_heartbeat, daemon=True, name="CentralHeartbeatThread"
        )
        self._heartbeat_thread.start()

    def authenticate_charging_point(self):
        """
        认证充电点


        """
        self.logger.debug(f"Authenticating charging point {self.args.id_cp}")
        if not self.central_conn_mgr.is_connected:
            self.logger.error("Cannot authenticate: not connected to Central.")
            return False
        auth_message = {
            "type": "auth_request",
            "message_id": str(uuid.uuid4()),
            "id": self.args.id_cp,
            "timestamp": int(time.time()),
        }
        return self.central_conn_mgr.send(auth_message)

    def _update_last_health_response(self):
        """
        更新最后一次收到Engine健康检查响应的时间。
        这个方法由MonitorMessageDispatcher在收到health_check_response时调用。
        """
        self._last_health_response_time = time.time()

    def _check_engine_health(self):
        """
        检查EV_CP_E的健康状态。
        """
        self.logger.debug("Starting health check thread for EV_CP_E")
        # 初始化为当前时间，这样不会立即超时
        self._last_health_response_time = time.time()
        while (
            self.running and self.engine_conn_mgr and self.engine_conn_mgr.is_connected
        ):
            current_time = time.time()
            # 检查是否超过超时时间
            if (
                self._last_health_response_time is not None
                and current_time - self._last_health_response_time
                > self.ENGINE_HEALTH_TIMEOUT
            ):
                self.logger.error("EV_CP_E health check timeout. Reporting failure.")
                self._report_failure("EV_CP_E health check timeout")
                # 检查当前状态，如果是 STOPPED，不应该改为 FAULTY
                if self._current_status != Status.STOPPED.value:
                    self.update_cp_status("FAULTY")
                else:
                    self.logger.warning(
                        "CP is STOPPED by admin, ignoring health check timeout (not changing to FAULTY)"
                    )
                # 标记为断开，让 ConnectionManager 去重连。
                # 注意：此处更新CP status为FAULTY后，Engine CM会尝试重连，
                # 重连成功后，_handle_connection_status_change会导致重新启动健康检查线程，
                # 并且如果是正常状态，CP status会再次更新。
                break

            health_check_msg = {
                "type": "health_check_request",
                "message_id": str(uuid.uuid4()),
                "id": self.args.id_cp,
            }
            if self.engine_conn_mgr.send(health_check_msg):
                self.logger.debug("Health check sent to EV_CP_E")
            else:
                self.logger.error(
                    "Failed to send health check to EV_CP_E (might be disconnected internally)."
                )

            time.sleep(self.ENGINE_HEALTH_CHECK_INTERVAL)
        self.logger.debug("Health check thread for EV_CP_E has stopped.")

    def _report_failure(self, failure_info):
        """
        向central报告故障。
        """
        if not self.central_conn_mgr.is_connected:
            self.logger.warning(
                f"Not connected to Central, cannot report failure: {failure_info}"
            )
            return False
        failure_message = {
            "type": MessageTypes.FAULT_NOTIFICATION,
            "message_id": str(uuid.uuid4()),
            "id": self.args.id_cp,
            "failure_info": failure_info,
        }
        if self.central_conn_mgr.send(failure_message):
            self.logger.debug("Reported failure to Central.")
            return True
        else:
            self.logger.error(
                "Failed to report failure to Central (might be disconnected internally)."
            )
            return False

    def update_cp_status(self, status):
        """
        更新充电点状态，并向 Central 报告。
        """
        if self._current_status == status:
            self.logger.debug(f"CP status already {status}, no update needed.")
            return
        self.logger.debug(f"Updating charging point status to: {status}")
        self._current_status = status
        self.report_status_to_central(status)
        if status == "FAULTY":
            self._send_stop_command_to_engine()

    def report_status_to_central(self, status):
        """
        向central报告状态。
        """
        if not self.central_conn_mgr.is_connected:
            self.logger.warning(
                f"Not connected to Central, cannot send status update: {status}"
            )
            return False
        status_message = {
            "type": "status_update",
            "message_id": str(uuid.uuid4()),
            "id": self.args.id_cp,
            "status": status,
        }
        if self.central_conn_mgr.send(status_message):
            self.logger.debug(f"Status update sent to Central: {status}")
            return True
        else:
            self.logger.error(
                "Failed to send status update to Central (might be disconnected internally)."
            )
            return False

    def _send_cp_id_to_engine(self):
        """
        向Engine发送CP_ID初始化消息。
        这是Monitor连接Engine后的第一个消息，用于告知Engine其充电桩ID。
        """
        if not self.engine_conn_mgr.is_connected:
            self.logger.warning("Not connected to Engine, cannot send CP_ID.")
            return False

        init_message = {
            "type": "init_cp_id",
            "message_id": str(uuid.uuid4()),
            "cp_id": self.args.id_cp,
        }

        if self.engine_conn_mgr.send(init_message):
            self.logger.debug(
                f"✓  CP_ID '{self.args.id_cp}' sent to Engine for initialization."
            )
            return True
        else:
            self.logger.error(
                "Failed to send CP_ID to Engine (might be disconnected internally)."
            )
            return False

    def _send_stop_command_to_engine(self):
        """
        向Engine发送停止命令。
        """
        if not self.engine_conn_mgr.is_connected:
            self.logger.warning("Not connected to Engine, cannot send stop command.")
            return False
        stop_message = {
            MessageFields.TYPE: MessageTypes.STOP_CHARGING_COMMAND,
            MessageFields.MESSAGE_ID: str(uuid.uuid4()),
            MessageFields.CP_ID: self.args.id_cp,
            MessageFields.SESSION_ID: None,  # 这是一个紧急停止，没有特定的session_id
            "timestamp": int(time.time()),
        }
        if self.engine_conn_mgr.send(stop_message):
            self.logger.info("Stop charging command sent to Engine.")
            return True
        else:
            self.logger.error(
                "Failed to send stop command to Engine (might be disconnected internally)."
            )
            return False

    def _handle_start_charging_command(self, message):
        """
        处理来自Central的启动充电命令（转发）。

        重要：Monitor在转发命令后应立即更新状态为CHARGING，
        以便监控面板能够实时显示正确的状态。
        """
        self.logger.info("Received start charging command from Central.")
        
        # 检查Central是否连接
        if not self.central_conn_mgr or not self.central_conn_mgr.is_connected:
            self.logger.error(
                "Cannot accept start charging command: Central is not connected. "
                "New charge requests are rejected until Central reconnects."
            )
            return False
        
        cp_id = message.get("cp_id")
        session_id = message.get("session_id")
        driver_id = message.get("driver_id")
        price_per_kwh = message.get("price_per_kwh", 0.0)  # 从Central获取价格

        if not cp_id or not session_id:
            self.logger.error("Start charging command missing required fields.")
            return False
        if not self.engine_conn_mgr.is_connected:
            self.logger.error(
                "Cannot forward start charging command: not connected to Engine."
            )
            return False

        # 转发启动充电命令到Engine
        start_charging_message = {
            "type": "start_charging_command",
            "message_id": str(uuid.uuid4()),
            "cp_id": cp_id,
            "session_id": session_id,
            "driver_id": driver_id,
            "price_per_kwh": price_per_kwh,
        }
        if self.engine_conn_mgr.send(start_charging_message):
            self.logger.info(
                f"Start charging command sent to Engine for session {session_id}, price: €{price_per_kwh}/kWh."
            )
            # 立即更新Monitor状态为CHARGING
            # 这样监控面板能够实时显示正确的状态
            self.update_cp_status(Status.CHARGING.value)
            self.logger.info(
                f"Monitor status updated to CHARGING for session {session_id}"
            )
            return True
        else:
            self.logger.error("Failed to send start charging command to Engine.")
            return False

    def _handle_charging_data_from_engine(self, message):
        """
        处理来自Engine的充电数据（转发并存储用于显示）。
        """
        self.logger.debug("Received charging data from Engine.")
        if not self.central_conn_mgr.is_connected:
            self.logger.warning(
                "Not connected to Central, cannot forward charging data."
            )
            return False

        # Validate required fields from Engine message
        required_fields = [
            "session_id",
            "energy_consumed_kwh",
            "total_cost",
        ]
        missing_fields = [
            field for field in required_fields if message.get(field) is None
        ]
        if missing_fields:
            self.logger.error(
                f"Charging data from Engine missing required fields: {', '.join(missing_fields)}"
            )
            return False
        
        # 存储充电数据用于状态面板显示
        session_id = message.get("session_id")
        energy_consumed_kwh = message.get("energy_consumed_kwh")
        total_cost = message.get("total_cost")
        
        # 更新或创建充电数据记录
        if not self._current_charging_data or self._current_charging_data.get("session_id") != session_id:
            # 新会话，初始化数据
            self._current_charging_data = {
                "session_id": session_id,
                "driver_id": message.get("driver_id", "unknown"),
                "start_time": time.time(),
            }
        
        # 更新实时数据
        self._current_charging_data["energy_consumed_kwh"] = energy_consumed_kwh
        self._current_charging_data["total_cost"] = total_cost
        self._current_charging_data["last_update"] = time.time()
        
        charging_data_message = {
            "type": "charging_data",
            "message_id": str(uuid.uuid4()),
            "cp_id": self.args.id_cp,
            "session_id": session_id,
            "energy_consumed_kwh": energy_consumed_kwh,
            "total_cost": total_cost,
        }
        if self.central_conn_mgr.send(charging_data_message):
            self.logger.debug("Charging data forwarded to Central.")
            return True
        else:
            self.logger.error("Failed to forward charging data to Central.")
            return False

    def _handle_charging_completion_from_engine(self, message):
        """
        处理来自Engine的充电完成通知（转发）。

        重要：Monitor在转发充电完成消息后应更新状态为ACTIVE，
        表示充电桩已完成充电并恢复到可用状态。
        
        如果Central断开，消息会堆积在队列中，等待Central恢复后发送。
        """
        self.logger.info("Received charging completion from Engine.")
        
        # Validate required fields from Engine message
        required_fields = ["session_id", "energy_consumed_kwh", "total_cost"]
        missing_fields = [
            field for field in required_fields if message.get(field) is None
        ]
        if missing_fields:
            self.logger.error(
                f"Charging completion from Engine missing required fields: {', '.join(missing_fields)}"
            )
            return False

        session_id = message.get("session_id")

        completion_message = {
            "type": "charge_completion",
            "message_id": message.get("message_id"),
            "cp_id": message.get("cp_id"),
            "session_id": session_id,
            "energy_consumed_kwh": message.get("energy_consumed_kwh"),
            "total_cost": message.get("total_cost"),
        }
        
        # 检查Central是否连接
        if not self.central_conn_mgr or not self.central_conn_mgr.is_connected:
            # Central断开，堆积消息
            with self._pending_messages_lock:
                self._pending_messages_to_central.append(completion_message)
            self.logger.warning(
                f"Central is not connected. Charging completion message for session {session_id} "
                f"has been queued. Will send when Central reconnects. "
                f"Queue size: {len(self._pending_messages_to_central)}"
            )
            # 即使Central断开，也要更新状态为ACTIVE（充电已完成）
            self.update_cp_status(Status.ACTIVE.value)
            # 清除充电数据（充电完成）
            self._current_charging_data = None
            return True
        
        # Central已连接，立即发送
        if self.central_conn_mgr.send(completion_message):
            self.logger.info("Charging completion forwarded to Central.")
            # 更新Monitor状态为ACTIVE（充电完成，恢复可用状态）
            # 这样监控面板能够实时显示正确的状态
            self.update_cp_status(Status.ACTIVE.value)
            # 清除充电数据（充电完成）
            self._current_charging_data = None
            self.logger.info(
                f"Monitor status updated to ACTIVE after charging completion for session {session_id}"
            )
            return True
        else:
            self.logger.error("Failed to forward charging completion to Central.")
            # 发送失败，也堆积消息
            with self._pending_messages_lock:
                self._pending_messages_to_central.append(completion_message)
            self.logger.warning(
                f"Failed to send charging completion. Message queued for session {session_id}. "
                f"Queue size: {len(self._pending_messages_to_central)}"
            )
            return False

    def _send_pending_messages_to_central(self):
        """
        发送堆积的消息到Central
        
        当Central重新连接后，发送所有堆积的charge_completion消息
        """
        if not self.central_conn_mgr or not self.central_conn_mgr.is_connected:
            self.logger.debug("Central is not connected, cannot send pending messages")
            return
        
        with self._pending_messages_lock:
            if not self._pending_messages_to_central:
                self.logger.debug("No pending messages to send to Central")
                return
            
            pending_count = len(self._pending_messages_to_central)
            self.logger.info(
                f"Central reconnected. Sending {pending_count} pending message(s) to Central..."
            )
            
            # 发送所有堆积的消息
            sent_count = 0
            failed_count = 0
            for message in self._pending_messages_to_central:
                session_id = message.get("session_id", "unknown")
                if self.central_conn_mgr.send(message):
                    sent_count += 1
                    self.logger.info(
                        f"✓ Pending charge_completion message for session {session_id} sent to Central"
                    )
                else:
                    failed_count += 1
                    self.logger.error(
                        f"✗ Failed to send pending charge_completion message for session {session_id}"
                    )
            
            # 清空队列（无论成功或失败，都清空，避免重复发送）
            self._pending_messages_to_central.clear()
            
            self.logger.info(
                f"Pending messages sent: {sent_count} successful, {failed_count} failed"
            )

    def _handle_message_from_engine(self, source_name: str, message: dict):
        """处理来自EV_CP_E的消息"""
        # source_name 由ConnectionManager提供，这里我们直接使用"Engine"
        self.message_dispatcher.dispatch_message("Engine", message)

    def _handle_message_from_central(self, source_name: str, message: dict):
        """处理来自central的消息"""
        # source_name 由ConnectionManager提供，这里我们直接使用"Central"
        self.message_dispatcher.dispatch_message("Central", message)

    def _graceful_shutdown(self):
        """
        执行有序的系统关闭。
        """
        self.logger.debug("Initiating graceful shutdown.")
        self.running = False  # 首先，通知所有应用层循环停止

        # 停止CLI
        self._stop_cli()

        # 停止状态面板
        self._stop_status_panel()

        # 停止所有 ConnectionManager
        if self.central_conn_mgr:
            self.central_conn_mgr.stop()
        if self.engine_conn_mgr:
            self.engine_conn_mgr.stop()
        # 等待 EV_CP_M 自身的业务逻辑线程 (心跳、健康检查) 结束
        # 由于它们是守护线程并且循环条件依赖 self.running 和 conn_mgr.is_connected，
        # 在 `running = False` 和 `conn_mgr.stop()` 后，它们应该会自然终止。
        # 这里可以加入适当的 `join` 来确保它们真的退出了，或者依赖 `daemon=True` 的性质。
        # 如果是 daemon=True，在主线程退出后，它们会被强制终止，这在大多数情况下是接受的。
        # 为了更明确的控制，可以在 `_send_heartbeat` 和 `_check_engine_health` 中加一个事件标志来立即停止。
        self.logger.debug("All connection managers stopped. Main loop will now exit.")

        self.logger.debug("Shutdown complete")

    def _start_cli(self):
        """启动Monitor CLI"""
        try:
            from Charging_point.Monitor.MonitorCLI import MonitorCLI

            self.logger.debug("Starting Monitor CLI...")
            self.cli = MonitorCLI(self, self.logger)
            self.cli.start()
            self.logger.debug("Monitor CLI started")

        except ImportError as e:
            self.logger.error(f"Unable to import MonitorCLI: {e}")
            self.logger.error("Please ensure MonitorCLI.py file exists")
        except Exception as e:
            self.logger.error(f"Failed to start CLI: {e}")

    def _stop_cli(self):
        """停止Monitor CLI"""
        if self.cli:
            self.logger.debug("Stopping Monitor CLI...")
            self.cli.stop()
            self.cli = None

    def _start_status_panel(self):
        """启动状态监控面板"""
        if not self._auto_start_panel:
            self.logger.debug("Panel can be manually started via CLI commands")
            return

        try:
            from Charging_point.Monitor.MonitorStatusPanel import MonitorStatusPanel

            self.logger.info("Starting Monitor status panel...")
            self.status_panel = MonitorStatusPanel(self)
            self.status_panel.start()
            self.logger.info("Monitor status panel started")
            # 通知CLI面板已激活
            if self.cli:
                self.cli.panel_active = True

        except ImportError as e:
            self.logger.error(f"Unable to import MonitorStatusPanel: {e}")
            self.logger.error("Please ensure MonitorStatusPanel.py file exists")
        except Exception as e:
            self.logger.error(f"Failed to start status panel: {e}")

    def _stop_status_panel(self):
        """停止状态监控面板"""
        if self.status_panel:
            self.logger.info("Stopping Monitor status panel...")
            self.status_panel.stop()
            self.status_panel = None
            # 通知CLI面板已停止
            if self.cli:
                self.cli.panel_active = False

    def initialize_systems(self):
        """
        初始化系统，创建 ConnectionManager 实例并启动它们。
        """
        self.logger.debug("Initializing connection managers...")

        # 创建 Central 的 ConnectionManager
        self.central_conn_mgr = ConnectionManager(
            self.args.ip_port_ev_central[0],
            self.args.ip_port_ev_central[1],
            "Central",
            self.logger,
            self._handle_message_from_central,  # 消息回调
            self._handle_connection_status_change,  # 连接状态回调
        )
        self.central_conn_mgr.start()
        # 创建 Engine 的 ConnectionManager
        self.engine_conn_mgr = ConnectionManager(
            self.args.ip_port_ev_cp_e[0],
            self.args.ip_port_ev_cp_e[1],
            "Engine",
            self.logger,
            self._handle_message_from_engine,  # 消息回调
            self._handle_connection_status_change,  # 连接状态回调
        )
        self.engine_conn_mgr.start()
        self.logger.debug("Connection managers started. Waiting for connections...")

        # 启动CLI (总是启动，用于控制面板)
        self._start_cli()

        # 启动状态面板(如果配置为自动启动)
        self._start_status_panel()

    def start(self):
        self.running = True
        self.logger.debug(f"Starting EV_CP_M module (ID: {self.args.id_cp})")
        self.logger.debug(
            f"Configured for EV_CP_E at {self.args.ip_port_ev_cp_e[0]}:{self.args.ip_port_ev_cp_e[1]}"
        )
        self.logger.debug(
            f"Configured for EV_Central at {self.args.ip_port_ev_central[0]}:{self.args.ip_port_ev_central[1]}"
        )
        self.initialize_systems()
        try:
            while self.running:
                time.sleep(0.1)  # 主循环，等待管理器和回调函数处理事件
        except KeyboardInterrupt:
            self.logger.debug("Keyboard interrupt detected. Shutting down EV_CP_M.")
        except Exception as e:
            self.logger.error(
                f"Unexpected error in EV_CP_M main loop: {e}", exc_info=True
            )
        finally:
            self.logger.debug(
                "EV_CP_M main loop terminated. Performing graceful shutdown."
            )
            self._graceful_shutdown()
            self.logger.debug("EV_CP_M has completely stopped.")


if __name__ == "__main__":
    import logging
    config = ConfigManager()
    debug_mode = config.get_debug_mode()
    if not debug_mode:
        logger = CustomLogger.get_logger(level=logging.INFO)
    else:
        logger = CustomLogger.get_logger(level=logging.DEBUG)

    ev_cp_m = EV_CP_M(logger=logger)
    ev_cp_m.start()
