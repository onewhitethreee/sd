"""
Estado de charging point
"""
from enum import Enum

class Status(Enum):
    ACTIVE = "ACTIVE" # Activo
    STOPPED = "STOPPED" # Parado
    CHARGING = "CHARGING" # Cargando
    FAULTY = "FAULTY" # Averiado
    DISCONNECTED = "DISCONNECTED" # Desconectado
