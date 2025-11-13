"""
Constante para todos los tipos de mensajes utilizados en el sistema de carga
"""


class MessageTypes:
    """
    Constantes de tipos de mensajes
    """

    # ==================== Constantes de mensajes de Engine ====================

    # Constante que son enviadas por el Monitor al Engine
    INIT_CP_ID = "init_cp_id"
    HEALTH_CHECK_REQUEST = "health_check_request"
    START_CHARGING_COMMAND = "start_charging_command"
    STOP_CHARGING_COMMAND = "stop_charging_command" 

    # Constante que son enviadas por el Engine al Monitor
    HEALTH_CHECK_RESPONSE = "health_check_response"
    COMMAND_RESPONSE = "command_response"
    ERROR_RESPONSE = "error_response"
    CHARGING_DATA = "charging_data"
    CHARGE_COMPLETION = "charge_completion"

    # ==================== Constantes de mensajes de Monitor ====================

    # Constante que son enviadas por el central al Monitor
    REGISTER_REQUEST = "register_request"
    HEARTBEAT_REQUEST = "heartbeat_request"
    AUTH_REQUEST = "auth_request"
    FAULT_NOTIFICATION = "fault_notification"
    STATUS_UPDATE = "status_update"
    RECOVERY_NOTIFICATION = "recovery_notification"
    CHARGING_DATA_RESPONSE = "charging_data_response"
    STATUS_UPDATE_RESPONSE = "status_update_response"
    CHARGE_COMPLETION_RESPONSE = "charge_completion_response"
    FAULT_NOTIFICATION_RESPONSE = "fault_notification_response"
    # Constante que son enviadas por el Central al Monitor
    STOP_CHARGING_SESSION_COMMAND = "stop_charging_session_command"  # Central -> Monitor (detener sesión de carga, estado→ACTIVE)
    STOP_CP_COMMAND = "stop_cp_command"  # Central -> Monitor (detener servicio del CP, estado→STOPPED)
    RESUME_CP_COMMAND = "resume_cp_command"  # Central -> Monitor (reanudar servicio del CP, estado→ACTIVE)

    # Constante que son enviadas por el Monitor al Central
    AUTH_RESPONSE = "auth_response"
    REGISTER_RESPONSE = "register_response"
    HEARTBEAT_RESPONSE = "heartbeat_response"

    # ==================== Constantes de mensajes de Driver ====================

    # Constante que son enviadas por el Driver al Central
    CHARGE_REQUEST = "charge_request"
    STOP_CHARGING_REQUEST = "stop_charging_request"
    AVAILABLE_CPS_REQUEST = "available_cps_request"
    CHARGING_HISTORY_REQUEST = "charging_history_request" 

    # Constante que son enviadas por el Central al Driver
    CHARGE_REQUEST_RESPONSE = "charge_request_response"
    CHARGING_STATUS_UPDATE = "charging_status_update"
    STOP_CHARGING_RESPONSE = "stop_charging_response"
    AVAILABLE_CPS_RESPONSE = "available_cps_response"
    CHARGING_HISTORY_RESPONSE = "charging_history_response"  

    # ==================== Constantes de mensajes de Admin ====================

    MANUAL_COMMAND = "manual_command"

    # ==================== Constantes de mensajes de sistema ====================

    CONNECTION_LOST = "connection_lost"
    CONNECTION_ERROR = "connection_error"


class ResponseStatus:
    """
    Constantes de estado de respuesta
    """
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"


class MessageFields:
    """
    Constantes de campos de mensajes
    """
    # campos comunes
    TYPE = "type"
    MESSAGE_ID = "message_id"
    TIMESTAMP = "timestamp"

    # campos de identificación
    CP_ID = "cp_id"
    DRIVER_ID = "driver_id"
    SESSION_ID = "session_id"

    # estado y errores
    STATUS = "status"
    MESSAGE = "message"
    ERROR = "error"
    REASON = "reason"

    # de carga
    ENERGY_CONSUMED_KWH = "energy_consumed_kwh"
    TOTAL_COST = "total_cost"
    PRICE_PER_KWH = "price_per_kwh"

    # otros
    CHARGING_POINTS = "charging_points"
    FAULT_TYPE = "fault_type"
    ENGINE_STATUS = "engine_status"
    IS_CHARGING = "is_charging"
    PROGRESS = "progress"
