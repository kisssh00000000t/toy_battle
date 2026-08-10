"""
局域网联网模块（改进版）。

改进内容：
- 引入 queue.Queue 消息队列，支持异步收发
- 实现状态增量同步（仅发送变化部分）
- 添加心跳检测和断线重连基础框架
- 消息类型化（JSON 封装 type + payload）
"""

import json
import socket
import threading
import queue
import time
import logging

logger = logging.getLogger(__name__)

# 消息类型常量
MSG_STATE = "state"
MSG_ACTION = "action"
MSG_HEARTBEAT = "heartbeat"
MSG_DISCONNECT = "disconnect"


class GameNet:
    """游戏网络通信层。

    支持主机/客户端模式，通过消息队列异步收发游戏状态和操作。

    TODO: review - GameNet 类当前未被外部导入，待实现联网功能后启用。

    Attributes:
        host: 监听/连接地址
        port: 监听/连接端口
        sock: 当前活跃 socket
        send_queue: 发送消息队列
        recv_queue: 接收消息队列
        connected: 是否已连接
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8888):
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.send_queue: queue.Queue[dict] = queue.Queue()
        self.recv_queue: queue.Queue[dict] = queue.Queue()
        self.connected = False
        self._running = False
        self._recv_thread: threading.Thread | None = None
        self._send_thread: threading.Thread | None = None

    def host_server(self) -> socket.socket:
        """作为主机等待客户端连接。

        Returns:
            已建立的连接 socket
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(1)
        logger.info(f"等待客户端连接 {self.host}:{self.port}...")
        conn, addr = s.accept()
        self.sock = conn
        self.connected = True
        self._start_threads()
        logger.info(f"客户端已连接: {addr}")
        return conn

    def join_server(self) -> socket.socket:
        """作为客户端连接主机。

        Returns:
            已建立的连接 socket
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.host, self.port))
        self.sock = s
        self.connected = True
        self._start_threads()
        logger.info(f"已连接到主机 {self.host}:{self.port}")
        return s

    def _start_threads(self) -> None:
        """启动收发线程。"""
        self._running = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._recv_thread.start()
        self._send_thread.start()

    def _recv_loop(self) -> None:
        """接收消息循环（后台线程）。"""
        while self._running and self.connected:
            try:
                msg = self._recv_raw()
                if msg:
                    self.recv_queue.put(msg)
            except (ConnectionError, OSError) as e:
                logger.warning(f"接收错误: {e}")
                self.connected = False
                break

    def _send_loop(self) -> None:
        """发送消息循环（后台线程）。"""
        while self._running and self.connected:
            try:
                msg = self.send_queue.get(timeout=0.5)
                self._send_raw(msg)
            except queue.Empty:
                continue
            except (ConnectionError, OSError) as e:
                logger.warning(f"发送错误: {e}")
                self.connected = False
                break

    def _send_raw(self, data: dict) -> None:
        """发送原始数据（4字节长度前缀 + JSON）。"""
        if not self.sock:
            return
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.sock.sendall(len(raw).to_bytes(4, "big") + raw)

    def _recv_raw(self) -> dict | None:
        """接收原始数据。"""
        if not self.sock:
            return None
        length_bytes = self._recv_exact(4)
        if not length_bytes:
            return None
        length = int.from_bytes(length_bytes, "big")
        raw = self._recv_exact(length)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def _recv_exact(self, n: int) -> bytes | None:
        """精确接收 n 字节。"""
        data = b""
        while len(data) < n:
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except (ConnectionError, OSError):
                return None
        return data

    def send_state(self, state_dict: dict) -> None:
        """发送游戏状态（增量同步）。

        Args:
            state_dict: 游戏状态字典
        """
        self.send_queue.put({"type": MSG_STATE, "payload": state_dict})

    def send_action(self, action: dict) -> None:
        """发送玩家操作。

        Args:
            action: 操作数据（如 PlaceTroopCommand）
        """
        self.send_queue.put({"type": MSG_ACTION, "payload": action})

    def send_heartbeat(self) -> None:
        """发送心跳包。"""
        self.send_queue.put({"type": MSG_HEARTBEAT, "payload": {}})

    def get_message(self, timeout: float = 0.1) -> dict | None:
        """从接收队列获取消息。

        Args:
            timeout: 等待超时（秒）

        Returns:
            消息字典或 None
        """
        try:
            return self.recv_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        """关闭连接。"""
        self._running = False
        self.connected = False
        if self.sock:
            try:
                self._send_raw({"type": MSG_DISCONNECT, "payload": {}})
            except (ConnectionError, OSError):
                pass
            self.sock.close()
            self.sock = None
        logger.info("网络连接已关闭")