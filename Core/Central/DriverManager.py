"""
Driver连接和会话管理类

负责：
1. Driver的连接/断开管理
2. Driver与client_id的映射
3. Driver活跃会话的快速查询（委托给ChargingSession）
"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


class DriverManager:
    """
    司机连接和会话管理类

    职责：
    - 管理Driver与客户端连接的映射关系
    - 提供Driver连接状态查询
    - 委托ChargingSession管理器查询活跃会话（避免数据冗余）
    """

    def __init__(self, logger, charging_session_manager):
        """
        初始化DriverManager

        Args:
            logger: 日志记录器
            charging_session_manager: ChargingSession管理器实例
        """
        self.logger = logger
        self.charging_session_manager = charging_session_manager

        # 只维护连接映射（单一职责）
        self._driver_connections = {}  # {driver_id: client_id}
        self._client_to_driver = {}  # {client_id: driver_id}

    def register_driver_connection(self, driver_id: str, client_id: str) -> bool:
        """
        注册Driver连接

        Args:
            driver_id: 司机ID
            client_id: 客户端连接ID

        Returns:
            bool: 是否成功注册
        """
        try:
            # 检查是否已经注册过
            if driver_id in self._driver_connections:
                old_client_id = self._driver_connections[driver_id]
                if old_client_id != client_id:
                    self.logger.warning(
                        f"Driver {driver_id} 重新连接 "
                        f"(旧连接: {old_client_id}, 新连接: {client_id})"
                    )
                    # 清理旧的反向映射
                    if old_client_id in self._client_to_driver:
                        del self._client_to_driver[old_client_id]
                else:
                    self.logger.debug(f"Driver {driver_id} already registered, skipping")
                    return True

            # 注册新连接
            self._driver_connections[driver_id] = client_id
            self._client_to_driver[client_id] = driver_id
            self.logger.debug(f"Driver {driver_id} connected (client: {client_id})")
            return True

        except Exception as e:
            self.logger.error(f"Failed to register Driver connection: {e}")
            return False

    def get_driver_client_id(self, driver_id: str) -> str | None:
        """
        获取Driver的连接ID

        Args:
            driver_id: 司机ID

        Returns:
            str | None: 客户端连接ID，如果未连接返回None
        """
        return self._driver_connections.get(driver_id)

    def get_driver_by_client_id(self, client_id: str) -> str | None:
        """
        根据客户端ID查找Driver

        Args:
            client_id: 客户端连接ID

        Returns:
            str | None: 司机ID，如果不是Driver连接返回None
        """
        return self._client_to_driver.get(client_id)

    def is_driver_connected(self, driver_id: str) -> bool:
        """
        检查Driver是否在线

        Args:
            driver_id: 司机ID

        Returns:
            bool: 是否在线
        """
        return driver_id in self._driver_connections

    def get_driver_active_sessions(self, driver_id: str) -> list:
        """
        获取Driver的活跃会话（委托给ChargingSession）

        这样避免数据重复存储，数据库作为唯一真实来源

        Args:
            driver_id: 司机ID

        Returns:
            list: 活跃会话列表
        """
        try:
            return self.charging_session_manager.get_active_sessions_for_driver(
                driver_id
            )
        except Exception as e:
            self.logger.error(f"Failed to get active sessions for Driver {driver_id}: {e}")
            return []

    def handle_driver_disconnect(self, client_id: str) -> tuple[str | None, list]:
        """
        处理Driver断开连接

        Args:
            client_id: 客户端连接ID

        Returns:
            tuple: (driver_id, active_session_ids)
            - driver_id: 断开的司机ID，如果不是Driver连接返回None
            - active_session_ids: 该Driver的活跃会话ID列表
        """
        # 查找driver_id
        driver_id = self._client_to_driver.get(client_id)
        if not driver_id:
            self.logger.debug(f"Client {client_id} is not a Driver, skipping Driver disconnect handling")
            return None, []

        self.logger.warning(f"Driver {driver_id} (client {client_id}) disconnected")

        # 获取活跃会话
        active_sessions = self.get_driver_active_sessions(driver_id)
        session_ids = [session["session_id"] for session in active_sessions]

        if session_ids:
            self.logger.info(
                f"Driver {driver_id} has {len(session_ids)} active sessions to stop: {session_ids}"
            )
        else:
            self.logger.info(f"Driver {driver_id} has no active charging sessions")

        # 清理连接映射
        if driver_id in self._driver_connections:
            del self._driver_connections[driver_id]
        if client_id in self._client_to_driver:
            del self._client_to_driver[client_id]

        self.logger.info(f"Cleaned up connection information for Driver {driver_id}")
        return driver_id, session_ids

    def get_all_connected_drivers(self) -> list[str]:
        """
        获取所有在线Driver列表

        Returns:
            list: Driver ID列表
        """
        return list(self._driver_connections.keys())

    def get_connection_count(self) -> int:
        """
        获取当前连接的Driver数量

        Returns:
            int: 连接数量
        """
        return len(self._driver_connections)

    def unregister_driver_connection(self, driver_id: str) -> bool:
        """
        手动注销Driver连接（用于特殊情况）

        Args:
            driver_id: 司机ID

        Returns:
            bool: 是否成功注销
        """
        try:
            if driver_id not in self._driver_connections:
                self.logger.warning(f"Driver {driver_id} not connected, cannot unregister")
                return False

            client_id = self._driver_connections[driver_id]

            # 清理映射
            del self._driver_connections[driver_id]
            if client_id in self._client_to_driver:
                del self._client_to_driver[client_id]

            self.logger.info(f"Unregistered Driver {driver_id} connection")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unregister Driver {driver_id} connection: {e}")
            return False

    def get_driver_info(self, driver_id: str) -> dict | None:
        """
        获取Driver的连接信息摘要

        Args:
            driver_id: 司机ID

        Returns:
            dict | None: 包含连接状态和活跃会话的信息字典
        """
        if driver_id not in self._driver_connections:
            return None

        active_sessions = self.get_driver_active_sessions(driver_id)

        return {
            "driver_id": driver_id,
            "client_id": self._driver_connections[driver_id],
            "is_connected": True,
            "active_sessions_count": len(active_sessions),
            "active_session_ids": [s["session_id"] for s in active_sessions],
        }


if __name__ == "__main__":
    # 测试代码
    from Common.Config.CustomLogger import CustomLogger
    from Common.Database.SqliteConnection import SqliteConnection
    from Core.Central.ChargingSession import ChargingSession

    logger = CustomLogger.get_logger()
    db_manager = SqliteConnection("ev_central.db")
    charging_session_manager = ChargingSession(logger, db_manager)

    driver_manager = DriverManager(logger, charging_session_manager)

    # 测试注册连接
    driver_manager.register_driver_connection("driver_001", "client_123")
    print(f"Driver connections: {driver_manager.get_connection_count()}")

    # 测试查询
    print(f"Driver client_id: {driver_manager.get_driver_client_id('driver_001')}")
    print(f"Client's driver: {driver_manager.get_driver_by_client_id('client_123')}")

    # 测试断开
    driver_id, sessions = driver_manager.handle_driver_disconnect("client_123")
    print(f"Disconnected Driver: {driver_id}, active sessions: {sessions}")
