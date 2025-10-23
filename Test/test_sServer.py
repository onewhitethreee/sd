# 用来模拟一个新的充电桩注册到 EV_Central.py 服务器
import socket
import json
import time
import uuid

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from Common.Message.MessageFormatter import MessageFormatter
from Common.Message.MessageTransformer import MessageTransformer
from Common.Config.CustomLogger import CustomLogger

SERVER_HOST = "localhost"
SERVER_PORT = 5002  # 确保这个端口和 EV_Central.py 中的一致


def dict_to_message_list(message_dict):
    """
    将字典消息转换为字符串列表格式
    根据消息类型确定字段顺序
    """
    message_type = message_dict.get("type", "")

    # 定义各种消息类型的字段顺序
    field_order = {
        "register_request": ["type", "message_id", "id", "location", "price_per_kwh"],
        "heartbeat_request": ["type", "message_id", "id"],
        "charge_request": ["type", "message_id", "driver_id", "cp_id"],
        "available_cps_request": ["type", "message_id", "driver_id"],
    }

    fields = field_order.get(message_type, list(message_dict.keys()))
    result = []
    for field in fields:
        value = message_dict.get(field, "")
        result.append(str(value) if value is not None else "")

    return result


def send_message(sock, message_dict):
    """将消息编码并发送出去"""
    print(f"\n[客户端] 准备发送消息:")
    print(json.dumps(message_dict, indent=2))

    # 将字典转换为字符串列表
    message_list = dict_to_message_list(message_dict)
    print(f"[客户端] 转换后的消息列表: {message_list}")

    # 打包消息
    serialized_message = MessageFormatter.pack_message(message_list)
    print(f"[客户端] 发送的原始数据: {serialized_message}")
    sock.sendall(serialized_message)
    print("[客户端] 消息已发送！")


def receive_message(sock):
    """接收并解码来自服务器的消息"""
    print("\n[客户端] 等待服务器的回应...")

    buffer = b""  # 初始化缓冲区

    while True:
        # 接收数据
        data = sock.recv(4096)
        if not data:
            print("[客户端] 连接已关闭")
            return None

        buffer += data
        print(f"[客户端] 收到原始数据: {data}")

        # 尝试从缓冲区提取完整消息
        buffer, message_list = MessageFormatter.extract_complete_message(buffer)

        if message_list:
            print("[客户端] 收到服务器的回应:")
            print(f"[客户端] 解包后的消息列表: {message_list}")

            # 将字符串列表转换为字典
            message_dict = MessageTransformer.to_dict_with_defaults(message_list)
            print(f"[客户端] 转换后的消息字典:")
            print(json.dumps(message_dict, indent=2))
            return message_dict
        else:
            print("[客户端] 消息还未完整，继续接收...")


def main():
    # 创建一个 TCP/IP socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            # 连接到服务器
            print(f"[客户端] 正在连接到 {SERVER_HOST}:{SERVER_PORT}...")
            sock.connect((SERVER_HOST, SERVER_PORT))
            print("[客户端] 连接成功！")

            # --- 构造注册消息 ---
            # 这是一个模拟的新充电桩发出的注册请求
            register_message = {
                "type": "register_request",
                "message_id": str(uuid.uuid4()),  # 生成一个唯一的消息ID
                "id": "C1P9919",
                "location": "Testing Lab, Sector 7G",
                "price_per_kwh": 0.55,
            }

            # 发送注册消息
            send_message(sock, register_message)

            # 等待并接收服务器的响应
            receive_message(sock)

        except ConnectionRefusedError:
            print("[客户端] 连接失败！请确保 EV_Central.py 服务器正在运行。")
        except Exception as e:
            print(f"[客户端] 发生错误: {e}")
        finally:
            print("\n[客户端] 测试结束，关闭连接。")
            sock.close()


if __name__ == "__main__":
    # 等待1秒，确保服务器有足够的时间启动
    logger = CustomLogger.get_logger()
    time.sleep(1)
    main()
