"""
ChargingSessionRepository - 负责 ChargingSessions 表的所有数据库操作
"""

from Common.Database.BaseRepository import BaseRepository


class ChargingSessionRepository(BaseRepository):
    """
    Clase que maneja las operaciones de la base de datos para la tabla ChargingSessions.
    """

    def get_table_name(self):
        return "ChargingSessions"

    def create(self, session_id, cp_id, driver_id, start_time):
        """
        Crear una sesión de carga

        Args:
            session_id: ID de la sesión
            cp_id: ID del punto de carga
            driver_id: ID del conductor
            start_time: Hora de inicio

        Returns:
            bool: Si fue exitoso
        """
        try:
            query = """
                INSERT INTO ChargingSessions
                (session_id, cp_id, driver_id, start_time, status)
                VALUES (?, ?, ?, ?, ?)
            """
            self.execute_update(query, (session_id, cp_id, driver_id, start_time, "in_progress"))

            self.logger.debug(f"Sesión de carga {session_id} creada con éxito")
            return True
        except Exception as e:
            self.logger.error(f"Error al crear la sesión de carga {session_id}: {e}")
            return False

    def update(
        self,
        session_id,
        end_time=None,
        energy_consumed_kwh=None,
        total_cost=None,
        status=None,
    ):
        """
        Actualizar la sesión de carga

        Args:
            session_id: ID de la sesión
            end_time: Hora de fin (opcional)
            energy_consumed_kwh: Energía consumida (opcional)
            total_cost: Costo total (opcional)
            status: Estado (opcional)

        Returns:
            bool: Si fue exitoso
        """
        try:
            # 构建动态更新语句
            updates = []
            params = []

            if end_time is not None:
                updates.append("end_time = ?")
                params.append(end_time)

            if energy_consumed_kwh is not None:
                updates.append("energy_consumed_kwh = ?")
                params.append(energy_consumed_kwh)

            if total_cost is not None:
                updates.append("total_cost = ?")
                params.append(total_cost)

            if status is not None:
                updates.append("status = ?")
                params.append(status)

            if not updates:
                self.logger.warning(f"Actualización de la sesión {session_id} sin campos proporcionados")
                return False

            params.append(session_id)
            query = f"UPDATE ChargingSessions SET {', '.join(updates)} WHERE session_id = ?"

            self.execute_update(query, params)
            # self.logger.debug(f"Sesión de carga {session_id} actualizada con éxito")
            return True
        except Exception as e:
            self.logger.error(f"Error al actualizar la sesión de carga {session_id}: {e}")
            return False

    def get_by_id(self, session_id):
        """
        Obtener información de la sesión de carga por ID

        Args:
            session_id: ID de la sesión

        Returns:
            dict: Información de la sesión o None
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE session_id = ?
            """
            rows = self.execute_query(query, (session_id,))

            if rows:
                row = rows[0]
                return {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
            return None
        except Exception as e:
            self.logger.error(f"Error al obtener la sesión de carga {session_id}: {e}")
            return None

    def get_active_sessions(self):
        """
        Obtener todos los sesiones de carga activas

        Returns:
            list: Lista de sesiones activas
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE status = 'in_progress'
            """
            rows = self.execute_query(query)

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"Error al obtener las sesiones de carga activas: {e}")
            return []

    def get_all(self):
        """
        Obtener todos los puntos de carga (incluidas las sesiones históricas)

        Returns:
            list: Lista de todas las sesiones
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                ORDER BY start_time DESC
            """
            rows = self.execute_query(query)

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"Failed to get all charging sessions: {e}")
            return []

    def get_active_sessions_by_charging_point(self, cp_id):
        """
        Obtener todas las sesiones de carga activas por punto de carga

        Args:
            cp_id: ID del punto de carga

        Returns:
            list: Lista de sesiones activas
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE cp_id = ? AND status = 'in_progress'
            """
            rows = self.execute_query(query, (cp_id,))

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"Error al obtener las sesiones de carga activas para el punto de carga {cp_id}: {e}")
            return []

    def get_active_sessions_by_driver(self, driver_id):
        """
        Obtener todas las sesiones de carga activas por conductor

        Args:
            driver_id: ID del conductor

        Returns:
            list: Lista de sesiones activas
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE driver_id = ? AND status = 'in_progress'
            """
            rows = self.execute_query(query, (driver_id,))

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"Error al obtener las sesiones de carga activas para el conductor {driver_id}: {e}")
            return []

    def get_sessions_by_charging_point(self, cp_id):
        """
        obtener todas las sesiones de un punto de carga (incluidas las históricas)

        Args:
            cp_id: ID del punto de carga

        Returns:
            list: Lista de sesiones
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE cp_id = ?
                ORDER BY start_time DESC
            """
            rows = self.execute_query(query, (cp_id,))

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"Error al obtener las sesiones para el punto de carga {cp_id}: {e}")
            return []

    def get_sessions_by_driver(self, driver_id):
        """
        Obtener todas las sesiones de un conductor (incluidas las históricas)

        Args:
            driver_id: ID del conductor

        Returns:
            list: Lista de sesiones
        """
        try:
            query = """
                SELECT session_id, cp_id, driver_id, start_time, end_time,
                       energy_consumed_kwh, total_cost, status
                FROM ChargingSessions
                WHERE driver_id = ?
                ORDER BY start_time DESC
            """
            rows = self.execute_query(query, (driver_id,))

            return [
                {
                    "session_id": row[0],
                    "cp_id": row[1],
                    "driver_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "energy_consumed_kwh": row[5],
                    "total_cost": row[6],
                    "status": row[7],
                }
                for row in rows
            ]
        except Exception as e:
            self.logger.error(f"Error al obtener las sesiones para el conductor {driver_id}: {e}")
            return []

    def exists(self, session_id):
        """
        Verificar si la sesión existe

        Args:
            session_id: ID de la sesión

        Returns:
            bool: Si existe
        """
        try:
            query = "SELECT 1 FROM ChargingSessions WHERE session_id = ?"
            rows = self.execute_query(query, (session_id,))
            return len(rows) > 0
        except Exception as e:
            self.logger.error(f"Error al verificar si la sesión {session_id} existe: {e}")
            return False

    def is_active(self, session_id):
        """
        Verificar si la sesión está activa

        Args:
            session_id: ID de la sesión

        Returns:
            bool: 是否活跃
        """
        try:
            session = self.get_by_id(session_id)
            return session is not None and session["status"] == "in_progress"
        except Exception as e:
            self.logger.error(f"Error al verificar si la sesión {session_id} está activa: {e}")
            return False
