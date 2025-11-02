"""
基础Repository类，定义通用的数据库操作接口
"""

from abc import ABC, abstractmethod
import logging


class BaseRepository(ABC):
    """
    抽象基类，定义所有Repository的通用接口和行为
    """

    def __init__(self, db_connection):
        """
        初始化Repository

        Args:
            db_connection: SqliteConnection实例，用于获取数据库连接
        """
        self.db_connection = db_connection
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_connection(self):
        """
        获取当前线程的数据库连接

        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        return self.db_connection.get_connection()

    def execute_query(self, query, params=None):
        """
        执行查询语句

        Args:
            query: SQL查询语句
            params: 查询参数（可选）

        Returns:
            list: 查询结果列表
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
            self.logger.error(f"执行查询失败: {e}")
            raise

    def execute_update(self, query, params=None):
        """
        执行更新语句（INSERT, UPDATE, DELETE）

        Args:
            query: SQL更新语句
            params: 更新参数（可选）

        Returns:
            int: 受影响的行数
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
            self.logger.error(f"执行更新失败: {e}")
            raise

    @abstractmethod
    def get_table_name(self):
        """
        获取Repository对应的表名

        Returns:
            str: 表名
        """
        pass
