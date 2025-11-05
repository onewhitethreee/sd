"""
DriverRepository 
"""
from datetime import datetime
from Common.Database.BaseRepository import BaseRepository


class DriverRepository(BaseRepository):
    """
    Clase que maneja las operaciones de la base de datos para la tabla Drivers.
    """

    def get_table_name(self):
        return "Drivers"

    def register(self, driver_id, username):
        """
        Registrar un conductor

        Args:
            driver_id: ID del conductor
            username: Nombre de usuario

        Returns:
            bool: Si fue exitoso
        """
        try:
            current_time = datetime.now().isoformat()

            query = """
                INSERT OR REPLACE INTO Drivers
                (driver_id, username, created_at)
                VALUES (?, ?, ?)
            """
            self.execute_update(query, (driver_id, username, current_time))

            self.logger.info(f"Conductor {driver_id} registrado con éxito")
            return True
        except Exception as e:
            self.logger.error(f"Error al registrar al conductor {driver_id}: {e}")
            return False

    def exists(self, driver_id):
        """
        Verificar si el conductor existe

        Args:
            driver_id: ID del conductor

        Returns:
            bool: Si existe
        """
        try:
            query = "SELECT 1 FROM Drivers WHERE driver_id = ?"
            rows = self.execute_query(query, (driver_id,))
            return len(rows) > 0
        except Exception as e:
            self.logger.error(f"Error al verificar si el conductor {driver_id} existe: {e}")
            return False

