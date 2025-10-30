"""
这个类应该封装所有关于充电桩的状态和数据。
只有一个权威的数据结构来存储充电桩信息：{cp_id: ChargingPointObject}。
ChargingPointObject 包含 location、price_per_kwh、status、last_connection_time，以及最重要的，当前的 client_id (如果已连接)。
它的职责包括：注册/更新充电桩、查询充电桩状态、管理充电桩与Socket客户端的映射。
所有的数据库操作（db_manager.insert_or_update_charging_point 等）都应该移到这里来。db_manager 成为它的一个依赖。
"""

import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from Common.Config.Status import Status
from Common.Database.SqliteConnection import SqliteConnection


class ChargingPoint:
    """
    充电桩管理类，负责充电桩的生命周期管理和状态维护。
    """

    def __init__(self, logger, db_manager):
        """
        初始化ChargingPoint管理器

        Args:
            logger: 日志记录器
            db_manager: 数据库管理器
        """
        self.logger = logger
        self.db_manager: SqliteConnection = db_manager
        # 连接映射：{cp_id: client_id}（仅保留连接映射，数据从数据库读取）
        self._cp_connections = {}
        # 反向映射：{client_id: cp_id}
        self._client_to_cp = {}

    def register_charging_point(
        self, cp_id, location, price_per_kwh, max_charging_rate_kw=11.0
    ):
        """
        注册一个新的充电桩

        Args:
            cp_id: 充电桩ID
            location: 位置
            price_per_kwh: 每度电价格
            max_charging_rate_kw: 最大充电速率（千瓦），默认11.0

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        try:
            # 验证价格
            price_per_kwh = float(price_per_kwh)
            if price_per_kwh < 0:
                return False, "price_per_kwh must be non-negative"

            # 验证充电速率
            max_charging_rate_kw = float(max_charging_rate_kw)
            if max_charging_rate_kw <= 0:
                return False, "max_charging_rate_kw must be positive"

            self.logger.debug(f"尝试将充电桩 {cp_id} 注册到数据库...")

            # 保存到数据库
            self.db_manager.insert_or_update_charging_point(
                cp_id=cp_id,
                location=location,
                price_per_kwh=price_per_kwh,
                status=Status.DISCONNECTED.value,
                last_connection_time=None,
                max_charging_rate_kw=max_charging_rate_kw,
            )

            self.logger.info(
                f"充电桩 {cp_id} 注册成功！(价格: €{price_per_kwh}/kWh, 最大速率: {max_charging_rate_kw}kW)"
            )
            return True, None

        except Exception as e:
            self.logger.error(f"注册充电桩 {cp_id} 失败: {e}")
            return False, str(e)

    def update_charging_point_connection(self, cp_id, client_id):
        """
        更新充电桩的连接信息

        Args:
            cp_id: 充电桩ID
            client_id: 客户端ID

        Returns:
            bool: 是否成功
        """
        try:
            # 检查充电桩是否已注册
            if not self.db_manager.is_charging_point_registered(cp_id):
                self.logger.warning(f"充电桩 {cp_id} 未注册")
                return False

            current_time = datetime.now(timezone.utc).isoformat()

            # 更新数据库
            self.db_manager.update_charging_point_status(
                cp_id=cp_id,
                status=Status.ACTIVE.value,
                last_connection_time=current_time,
            )

            # 更新连接映射
            self._cp_connections[cp_id] = client_id
            self._client_to_cp[client_id] = cp_id

            self.logger.info(f"充电桩 {cp_id} 连接已更新，客户端: {client_id}")
            return True

        except Exception as e:
            self.logger.error(f"更新充电桩 {cp_id} 连接失败: {e}")
            return False

    def update_charging_point_status(self, cp_id, status):
        """
        更新充电桩状态

        Args:
            cp_id: 充电桩ID
            status: 新状态

        Returns:
            bool: 是否成功
        """
        try:
            # 检查充电桩是否已注册
            if not self.db_manager.is_charging_point_registered(cp_id):
                self.logger.warning(f"充电桩 {cp_id} 未注册")
                return False

            # 更新数据库
            self.db_manager.update_charging_point_status(cp_id=cp_id, status=status)

            # self.logger.info(f"充电桩 {cp_id} 状态已更新为: {status}")
            return True

        except Exception as e:
            self.logger.error(f"更新充电桩 {cp_id} 状态失败: {e}")
            return False

    def get_charging_point(self, cp_id):
        """
        获取充电桩信息

        Args:
            cp_id: 充电桩ID

        Returns:
            dict: 充电桩信息或None
        """
        return self.db_manager.get_charging_point(cp_id)

    def is_charging_point_registered(self, cp_id):
        """
        检查充电桩是否已注册

        Args:
            cp_id: 充电桩ID

        Returns:
            bool: 是否已注册
        """
        return self.db_manager.is_charging_point_registered(cp_id)

    def get_charging_point_status(self, cp_id):
        """
        获取充电桩状态

        Args:
            cp_id: 充电桩ID

        Returns:
            str: 充电桩状态或None
        """
        return self.db_manager.get_charging_point_status(cp_id)

    def get_client_id_for_charging_point(self, cp_id):
        """
        获取充电桩对应的客户端ID

        Args:
            cp_id: 充电桩ID

        Returns:
            str: 客户端ID或None
        """
        return self._cp_connections.get(cp_id)

    def get_charging_point_id_for_client(self, client_id):
        """
        获取客户端对应的充电桩ID

        Args:
            client_id: 客户端ID

        Returns:
            str: 充电桩ID或None
        """
        return self._client_to_cp.get(client_id)

    def handle_client_disconnect(self, client_id):
        """
        处理客户端断开连接

        Args:
            client_id: 客户端ID

        Returns:
            str: 断开连接的充电桩ID或None
        """
        if client_id not in self._client_to_cp:
            return None

        cp_id = self._client_to_cp[client_id]

        try:
            # 更新数据库状态为离线
            self.db_manager.update_charging_point_status(
                cp_id=cp_id,
                status=Status.DISCONNECTED.value,
            )

            # 清理映射关系
            del self._cp_connections[cp_id]
            del self._client_to_cp[client_id]

            self.logger.warning(f"充电桩 {cp_id} 已断开连接")
            return cp_id

        except Exception as e:
            self.logger.error(f"处理充电桩 {cp_id} 断开连接失败: {e}")
            return cp_id

    def get_all_charging_points(self):
        """
        获取所有充电桩信息

        Returns:
            list: 所有充电桩信息列表
        """
        return self.db_manager.get_all_charging_points()

    def get_available_charging_points(self):
        """
        获取所有可用的充电桩（状态为ACTIVE）

        Returns:
            list: 可用充电桩列表
        """
        return self.db_manager.get_available_charging_points()
