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


class EV_CP_M:
    def __init__(self, logger=None):
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
        else:

            class Args:
                ip_port_ev_cp_e = self.config.get_ip_port_ev_cp_e()
                ip_port_ev_central = self.config.get_ip_port_ev_cp_central()
                import random
                id_cp = f"cp_{random.randint(0,99999)}"

            self.args = Args()
            self.logger.debug("Debug mode is ON. Using default arguments.")

        self.central_conn_mgr: ConnectionManager = None  # ConnectionManager 实例
        self.engine_conn_mgr: ConnectionManager = None  # ConnectionManager 实例
        self.running = False

        self._current_status = Status.DISCONNECTED.value  # 当前充电点状态

        self._heartbeat_thread = None
        self._engine_health_thread = None

        self.HEARTBEAT_INTERVAL = 30  # 向 Central 发送心跳的间隔（秒）
        self.ENGINE_HEALTH_TIMEOUT = (
            90  # 如果超过这个时间没有收到 Engine 的健康响应，则认为故障（秒）
        )
        self.ENGINE_HEALTH_CHECK_INTERVAL = 30  # 向 Engine 发送健康

        # 用于追踪最后一次收到Engine健康检查响应的时间
        self._last_health_response_time = None

        # 注册确认标志（修复竞态条件）
        self._registration_confirmed = False

        # 初始化消息分发器
        self.message_dispatcher = MonitorMessageDispatcher(self.logger, self)

    def _register_with_central(self):
        """
        和central注册一个charging point (现在由 ConnectionManager 发送)。
        """
        if not self.central_conn_mgr.is_connected:
            self.logger.warning("Not connected to Central, can't register.")
            return False
        if not self.engine_conn_mgr.is_connected:
            self.logger.warning("Not connected to Engine, can't register.")
            return False

        # 重置注册确认标志，等待 Central 响应
        self._registration_confirmed = False

        register_message = {
            "type": "register_request",
            "message_id": str(uuid.uuid4()),
            "id": self.args.id_cp,
            "location": f"Location_{random.randint(1,99999)}",
            "price_per_kwh": (random.uniform(0.15, 0.25)),
        }
        success = self.central_conn_mgr.send(register_message)
        if success:
            self.logger.info("Registration request sent to Central, waiting for confirmation...")
        return success

    def _handle_connection_status_change(self, source_name: str, status: str):
        """
        由 ConnectionManager 回调，处理连接状态变化。
        这就是 EV_CP_M 响应底层网络事件的核心逻辑。

        Según especificaciones (Guía de Corrección, página 3):
        Monitor_OK and Engine_OK => Activado (Verde)
        Monitor_OK and Engine_KO => Averiado (Rojo)
        Monitor_KO and Engine_OK => Desconectado (gestionado por Central)
        Monitor_KO and Engine_KO => Desconectado (gestionado por Central)
        """
        self.logger.debug(f"Connection status for {source_name} changed to {status}")
        if source_name == "Central":
            if status == "CONNECTED":
                self.logger.info("Central is now connected. Attempting to register...")
                # 确保注册在 Central 连接后进行
                self._register_with_central()
                # 启动 Central 的心跳线程
                self._start_heartbeat_thread()
                # Solo establecer ACTIVE si Engine también está conectado y funcionando
                # De lo contrario, esperar a que Engine confirme su estado
                if self.engine_conn_mgr and self.engine_conn_mgr.is_connected:
                    self._check_and_update_to_active()
                else:
                    self.logger.info("Waiting for Engine connection before setting ACTIVE status")
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
                self.logger.info(
                    "Engine is now connected. Initializing CP_ID..."
                )
                # ✅ 首先发送CP_ID初始化消息给Engine
                self._send_cp_id_to_engine()

                # 然后启动健康检查线程
                self._start_engine_health_check_thread()
                # Si Central también está conectado, actualizar a ACTIVE
                if self.central_conn_mgr and self.central_conn_mgr.is_connected:
                    self._check_and_update_to_active()
                else:
                    self.logger.info("Waiting for Central connection before setting ACTIVE status")
            elif status == "DISCONNECTED":
                self.logger.warning("Engine is disconnected. Reporting failure.")
                self._report_failure("EV_CP_E connection lost")
                # Monitor OK pero Engine KO => FAULTY
                self.update_cp_status(Status.FAULTY.value)
                self._stop_engine_health_check_thread()  # 停止健康检查

    def _handle_central_disconnection(self):
        """
        处理Central断开连接的情况

        当Central断开时：
        1. 如果正在充电，停止充电（因为无法向Central报告数据）
        2. 更新充电点状态为FAULTY
        3. ConnectionManager会自动尝试重连
        """
        self.logger.warning("Handling Central disconnection...")

        # 检查是否正在充电
        if self._current_status == Status.CHARGING.value:
            self.logger.warning(
                "Currently charging, but Central is disconnected. Stopping charging to prevent data loss."
            )
            # 向Engine发送停止命令
            self._send_stop_command_to_engine()
            self.logger.info(
                "Charging stopped due to Central disconnection. Will resume when Central reconnects."
            )

        # 更新状态为FAULTY（失去与Central的连接）
        self.update_cp_status(Status.FAULTY.value)
        self.logger.info(
            "CP status set to FAULTY due to Central disconnection. Waiting for reconnection..."
        )

    def _check_and_update_to_active(self):
        """
        检查是否满足ACTIVE状态的条件，并更新状态
        只有当Central和Engine都连接成功，且注册已确认时才更新为ACTIVE
        """
        if (
            self._registration_confirmed  # 新增：必须注册成功
            and self.central_conn_mgr
            and self.central_conn_mgr.is_connected
            and self.engine_conn_mgr
            and self.engine_conn_mgr.is_connected
        ):
            # 只有在当前状态不是ACTIVE时才更新
            if self._current_status != Status.ACTIVE.value:
                self.logger.info(
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
    # TODO 这里也没有停止啊？
    def _stop_engine_health_check_thread(self):
        """停止对 Engine 的健康检查线程"""
        if self._engine_health_thread and self._engine_health_thread.is_alive():
            self.logger.info("Stopping Engine health check thread.")
            # 通过设置 running 标志让线程自然退出
            # 这里假设线程会检查 self.running 和 conn_mgr.is_connected
            # 因为我们没有单独的停止事件，所以只能依赖这些条件
            # 实际上，线程会在下一次循环时检测到条件变化并退出
        else:
            self.logger.debug("Engine health check thread is not running.")

    def _stop_heartbeat_thread(self):
        """停止发送心跳的线程"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self.logger.info("Stopping heartbeat thread for Central.")
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
        self.logger.info("Starting Engine health check thread.")
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
        self.logger.info("Heartbeat thread for Central has stopped.")

    def _start_heartbeat_thread(self):
        """
        启动发送心跳的线程
        """
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self.logger.debug("Heartbeat thread for Central already running.")
            return
        self.logger.info("Starting heartbeat thread for Central.")
        self._heartbeat_thread = threading.Thread(
            target=self._send_heartbeat, daemon=True, name="CentralHeartbeatThread"
        )
        self._heartbeat_thread.start()

    # TODO 这里没有调用
    def authenticate_charging_point(self):
        """
        认证充电点，现在通过 ConnectionManager.send() 发送。
        """
        self.logger.info(f"Authenticating charging point {self.args.id_cp}")
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
        self.logger.info("Starting health check thread for EV_CP_E")
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
                self.update_cp_status("FAULTY")
                # 标记为断开，让 ConnectionManager 去重连。
                # 注意：此处更新CP status为FAULTY后，Engine CM会尝试重连，
                # 重连成功后，_handle_connection_status_change会导致重新启动健康检查线程，
                # 并且如果是正常状态，CP status会再次更新。
                break  # 退出循环，等待CM重连和新的健康检查线程启动

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
        self.logger.info("Health check thread for EV_CP_E has stopped.")

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
            "type": "fault_notification",
            "message_id": str(uuid.uuid4()),
            "id": self.args.id_cp,
            "failure_info": failure_info,
        }
        if self.central_conn_mgr.send(failure_message):
            self.logger.info("Reported failure to Central.")
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
        self.logger.info(f"Updating charging point status to: {status}")
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
            self.logger.info(f"Status update sent to Central: {status}")
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
            self.logger.info(f"✅ CP_ID '{self.args.id_cp}' sent to Engine for initialization.")
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
            "type": "stop_command",
            "message_id": str(uuid.uuid4()),
            "id": self.args.id_cp,
            "timestamp": int(time.time()),
        }
        if self.engine_conn_mgr.send(stop_message):
            self.logger.info("Stop command sent to Engine.")
            return True
        else:
            self.logger.error(
                "Failed to send stop command to Engine (might be disconnected internally)."
            )
            return False

    def _handle_start_charging_command(self, message):
        """
        处理来自Central的启动充电命令（转发）。
        """
        self.logger.info("Received start charging command from Central.")
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
            "price_per_kwh": price_per_kwh,  # 转发价格信息
        }
        if self.engine_conn_mgr.send(start_charging_message):
            self.logger.info(
                f"Start charging command sent to Engine for session {session_id}, price: €{price_per_kwh}/kWh."
            )
            return True
        else:
            self.logger.error("Failed to send start charging command to Engine.")
            return False

    def _handle_charging_data_from_engine(self, message):
        """
        处理来自Engine的充电数据（转发）。
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
        # TODO 这里用常量
        charging_data_message = {
            "type": "charging_data",
            "message_id": str(uuid.uuid4()),
            "cp_id": self.args.id_cp,
            "session_id": message.get("session_id"),
            "energy_consumed_kwh": message.get("energy_consumed_kwh"),
            "total_cost": message.get("total_cost"),
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
        """
        self.logger.info("Received charging completion from Engine.")
        if not self.central_conn_mgr.is_connected:
            self.logger.warning(
                "Not connected to Central, cannot forward charging completion."
            )
            return False

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
        # TODO 这里用response常量
        completion_message = {
            "type": "charge_completion",
            "message_id": message.get("message_id"),
            "cp_id": message.get("cp_id"),
            "session_id": message.get("session_id"),
            "energy_consumed_kwh": message.get("energy_consumed_kwh"),
            "total_cost": message.get("total_cost"),
        }
        if self.central_conn_mgr.send(completion_message):
            self.logger.info("Charging completion forwarded to Central.")
            return True
        else:
            self.logger.error("Failed to forward charging completion to Central.")
            return False

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
        self.logger.info("Initiating graceful shutdown.")
        self.running = False  # 首先，通知所有应用层循环停止
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
        self.logger.info("All connection managers stopped. Main loop will now exit.")
        # 原来的 _exit(0) 彻底移除！

        self.logger.info("Shutdown complete")

    def initialize_systems(self):
        """
        初始化系统，创建 ConnectionManager 实例并启动它们。
        """
        self.logger.info("Initializing connection managers...")

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
        self.logger.info("Connection managers started. Waiting for connections...")

    def start(self):
        self.running = True
        self.logger.info(f"Starting EV_CP_M module (ID: {self.args.id_cp})")
        self.logger.info(
            f"Configured for EV_CP_E at {self.args.ip_port_ev_cp_e[0]}:{self.args.ip_port_ev_cp_e[1]}"
        )
        self.logger.info(
            f"Configured for EV_Central at {self.args.ip_port_ev_central[0]}:{self.args.ip_port_ev_central[1]}"
        )
        self.initialize_systems()
        try:
            while self.running:
                time.sleep(1)  # 主循环，等待管理器和回调函数处理事件
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt detected. Shutting down EV_CP_M.")
        except Exception as e:
            self.logger.error(
                f"Unexpected error in EV_CP_M main loop: {e}", exc_info=True
            )
        finally:
            self.logger.info(
                "EV_CP_M main loop terminated. Performing graceful shutdown."
            )
            self._graceful_shutdown()
            self.logger.info("EV_CP_M has completely stopped.")


if __name__ == "__main__":
    logger = CustomLogger.get_logger()

    ev_cp_m = EV_CP_M(logger=logger)
    ev_cp_m.start()
