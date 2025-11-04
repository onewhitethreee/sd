
from abc import ABC, abstractmethod
import logging


class BaseRepository(ABC):
    """
    Clase base abstracta que define la interfaz y el comportamiento comunes para todos los repositorios.
    """

    def __init__(self, db_connection):
        """
        Inicializar el repositorio.

        Args:
            db_connection: Objeto de conexión a la base de datos
        """
        self.db_connection = db_connection
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_connection(self):
        """
        Obtener la conexión a la base de datos del hilo actual.

        Returns:
            sqlite3.Connection: Objeto de conexión a la base de datos.
        """
        return self.db_connection.get_connection()

    def execute_query(self, query, params=None):
        """
        Ejecutar una sentencia de consulta

        Args:
            query: sentencia SQL de consulta
            params: argumentos de consulta

        Returns:
            list: lista de resultados
        """
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
        except Exception as e:
            self.logger.error(f"Error al ejecutar la consulta: {e}")
            raise

    def execute_update(self, query, params=None):
        """
        Ejecutar una sentencia de actualización (INSERT, UPDATE, DELETE)

        Args:
            query: Sentencia SQL de actualización
            params: Parámetros de actualización (opcional)

        Returns:
            int: lineas afectadas
        """
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            connection.commit()
            return cursor.rowcount
        except Exception as e:
            connection.rollback()
            self.logger.error(f"Error al ejecutar la actualización: {e}")
            raise

    @abstractmethod
    def get_table_name(self):
        """
        obtener el nombre de la tabla asociada al repositorio

        Returns:
            str: Nombre de la tabla
        """
        pass
