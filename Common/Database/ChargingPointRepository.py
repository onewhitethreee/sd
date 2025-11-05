"""
ChargingPointRepository - 负责 ChargingPoints 表的所有数据库操作
"""


from Common.Database.BaseRepository import BaseRepository


class ChargingPointRepository(BaseRepository):
    """
    clase que maneja las operaciones de la base de datos para la tabla ChargingPoints.
    """

    def get_table_name(self):
        return "ChargingPoints"

    def insert_or_update(
        self,
        cp_id,
        location,
        price_per_kwh,
        status,
        last_connection_time,
    ):
        """
        Insertar o actualizar la información del punto de carga.

        Args:
            cp_id: ID del punto de carga
            location: Ubicación
            price_per_kwh: Precio por kWh
            status: Estado
            last_connection_time: Última hora de conexión

        Returns:
            bool: Si fue exitoso
        """
        try:
            query = """
                INSERT OR REPLACE INTO ChargingPoints
                (cp_id, location, price_per_kwh, status, last_connection_time)
                VALUES (?, ?, ?, ?, ?)
            """
            self.execute_update(
                query,
                (
                    cp_id,
                    location,
                    price_per_kwh,
                    status,
                    last_connection_time,
                ),
            )

            self.logger.info(
                f"El punto de carga {cp_id} se registró/actualizó correctamente, ubicación: {location}, precio: {price_per_kwh}, "
                f"estado: {status}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error al insertar/actualizar el punto de carga '{cp_id}': {e}")
            return False

    def update_status(self, cp_id, status, last_connection_time=None):
        """
        Actualizar el estado del punto de carga

        Args:
            cp_id: ID del punto de carga
            status: Nuevo estado
            last_connection_time: Última hora de conexión (opcional)

        Returns:
            bool: Si fue exitoso
        """
        try:
            if last_connection_time is not None:
                query = "UPDATE ChargingPoints SET status = ?, last_connection_time = ? WHERE cp_id = ?"
                self.execute_update(query, (status, last_connection_time, cp_id))
            else:
                query = "UPDATE ChargingPoints SET status = ? WHERE cp_id = ?"
                self.execute_update(query, (status, cp_id))

            return True
        except Exception as e:
            self.logger.error(f"Error al actualizar el estado del punto de carga {cp_id}: {e}")
            return False

    def update_last_connection_time(self, cp_id, last_connection_time):
        """
        Actualizar la última hora de conexión del punto de carga

        Args:
            cp_id: ID del punto de carga
            last_connection_time: Última hora de conexión

        Returns:
            bool: Si fue exitoso
        """
        try:
            query = "UPDATE ChargingPoints SET last_connection_time = ? WHERE cp_id = ?"
            self.execute_update(query, (last_connection_time, cp_id))
            return True
        except Exception as e:
            self.logger.error(f"Error al actualizar la última hora de conexión del punto de carga {cp_id}: {e}")
            return False

    def get_by_id(self, cp_id):
        """
        Obtener información del punto de carga por ID

        Args:
            cp_id: ID del punto de carga

        Returns:
            dict: Información del punto de carga, si no existe devuelve None
        """
        try:
            query = """
                SELECT cp_id, location, price_per_kwh, status, last_connection_time
                FROM ChargingPoints
                WHERE cp_id = ?
            """
            rows = self.execute_query(query, (cp_id,))

            if rows:
                row = rows[0]
                return {
                    "cp_id": row[0],
                    "location": row[1],
                    "price_per_kwh": row[2],
                    "status": row[3],
                    "last_connection_time": row[4],
                }
            return None
        except Exception as e:
            self.logger.error(f"Error al obtener información del punto de carga {cp_id}: {e}")
            return None

    def get_status(self, cp_id):
        """
        Obtener el estado del punto de carga

        Args:
            cp_id: ID del punto de carga


        Returns:
            str: Estado del punto de carga, si no existe devuelve None
        """
        try:
            query = "SELECT status FROM ChargingPoints WHERE cp_id = ?"
            rows = self.execute_query(query, (cp_id,))
            return rows[0][0] if rows else None
        except Exception as e:
            self.logger.error(f"Error al obtener el estado del punto de carga {cp_id}: {e}")
            return None

    def exists(self, cp_id):
        """
        Verificar si el punto de carga existe

        Args:
            cp_id: ID del punto de carga

        Returns:
            bool: Si existe
        """
        try:
            query = "SELECT 1 FROM ChargingPoints WHERE cp_id = ?"
            rows = self.execute_query(query, (cp_id,))
            return len(rows) > 0
        except Exception as e:
            self.logger.error(f"Error al verificar si el punto de carga {cp_id} existe: {e}")
            return False

    def get_all(self):
        """
        Obtener todos los puntos de carga

        Returns:
            list: Lista de puntos de carga
        """
        try:
            query = """
                SELECT cp_id, location, price_per_kwh, status, last_connection_time 
                FROM ChargingPoints
            """
            rows = self.execute_query(query)

            return [
                {
                    "cp_id": row[0],
                    "location": row[1],
                    "price_per_kwh": row[2],
                    "status": row[3],
                    "last_connection_time": row[4],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"Error al obtener todos los puntos de carga: {e}")
            return []

    def get_available(self):
        """
        Obtener todos los puntos de carga disponibles (estado ACTIVE)

        Returns:
            list: Lista de puntos de carga disponibles
        """
        try:
            query = """
                SELECT cp_id, location, price_per_kwh, status, last_connection_time
                FROM ChargingPoints
                WHERE status = ?
            """
            rows = self.execute_query(query, ("ACTIVE",))

            return [
                {
                    "cp_id": row[0],
                    "location": row[1],
                    "price_per_kwh": row[2],
                    "status": row[3],
                    "last_connection_time": row[4],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"Error al obtener los puntos de carga disponibles: {e}")
            return []

    def set_all_status(self, status):
        """
        Establecer el estado de todos los puntos de carga

        Args:
            status: Nuevo estado

        Returns:
            bool: Si fue exitoso
        """
        try:
            query = "UPDATE ChargingPoints SET status = ?"
            self.execute_update(query, (status,))
            return True
        except Exception as e:
            self.logger.error(f"Error al establecer el estado de todos los puntos de carga: {e}")
            return False
