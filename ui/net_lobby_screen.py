"""
局域网对战房间大厅界面（异步线程版）。

提供创建主机（红方先手）和加入主机（蓝方后手）两种操作，
通过 game.net.GameNet 建立 Socket 连接后切换到对应界面。

核心改进：
    - 创建主机/加入主机均在 daemon 线程中执行，避免 socket.accept()
      阻塞主 UI 线程导致窗口卡死
    - 使用 s.settimeout(0.5) 短轮询 + is_working 标志实现可取消的等待
    - 连接成功后由 update() 在主线程中执行 switch_to，保证线程安全

组件：
    NetLobbyScreen: 独立 Screen，物理隔离杜绝事件穿透
"""

import logging
import queue
import socket
import threading
import time

import pygame

from .base_screen import BaseScreen, play_stagger_spawn
from .widgets import ToyButton, ToyPanel, ToyTitle, TOY_COLORS, get_font

logger = logging.getLogger(__name__)


class NetLobbyScreen(BaseScreen):
    """局域网对战房间大厅 — 真正纯异步监听，绝不卡死主窗口"""

    def __init__(self, manager):
        super().__init__(manager)
        self.title = ToyTitle("局域网对战大厅", center_x=manager.WIN_W // 2,
                              center_y=100, font_size=56)
        self.panel = ToyPanel((manager.WIN_W // 2 - 240, 180, 480, 440))

        self.status_msg = "请选择：创建房间 (先手红方) 或 加入主机 (后手蓝方)"
        self.status_color = TOY_COLORS["dark_text"]

        bx = manager.WIN_W // 2 - 180
        # 核心修复：把 callback 明确指向异步的 _start_host_thread / _start_join_thread
        self.btn_host = ToyButton(
            "创建房间 (红方 · 监听8888)", rect=(bx, 240, 360, 66),
            callback=self._start_host_thread, color=TOY_COLORS["primary_yellow"],
        )
        self.btn_join = ToyButton(
            "加入对战 (蓝方 · 127.0.0.1)", rect=(bx, 340, 360, 66),
            callback=self._start_join_thread, color=TOY_COLORS["secondary_cyan"],
        )
        self.btn_back = ToyButton(
            "返回主菜单 / 取消监听", rect=(bx + 80, 460, 200, 56),
            callback=self._go_back, color=TOY_COLORS["danger_red"],
        )

        self.widgets = [self.title, self.btn_host, self.btn_join, self.btn_back]
        play_stagger_spawn(self, anim_dur=0.3, gap=0.08)

        self.is_working = False
        self.client_connected = False
        self.net_client = None
        self.is_host_mode = True
        self.server_sock = None

    def _start_host_thread(self):
        if self.is_working:
            return
        self.is_working = True
        self.is_host_mode = True
        self.client_connected = False
        self.btn_host.enabled = False
        self.btn_join.enabled = False
        self.status_msg = "正在监听 8888 端口等待对手接入... (窗口不会卡死)"
        self.status_color = TOY_COLORS["warm_orange"]
        threading.Thread(target=self._async_host_worker, daemon=True).start()

    def _async_host_worker(self):
        from game.net import GameNet
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock = s

        try:
            s.bind(("0.0.0.0", 8888))
            s.listen(1)
            s.settimeout(0.5)  # 500ms 轮询超时，确保主线程随时能通过 ESC 中断
            while self.is_working:
                try:
                    conn, addr = s.accept()
                except socket.timeout:
                    continue

                net = GameNet.__new__(GameNet)
                net.host = "0.0.0.0"
                net.port = 8888
                net.sock = conn
                net.send_queue = queue.Queue()
                net.recv_queue = queue.Queue()
                net.connected = True
                net._running = True
                net._start_threads()
                self.net_client = net
                self.client_connected = True
                return
        except Exception as e:
            self.status_msg = f"创建主机失败: {e}"
            self.status_color = TOY_COLORS["danger_red"]
            self.is_working = False
            self.btn_host.enabled = True
            self.btn_join.enabled = True
        finally:
            try:
                s.close()
            except Exception:
                pass
            self.server_sock = None

    def _start_join_thread(self):
        if self.is_working:
            return
        self.is_working = True
        self.is_host_mode = False
        self.client_connected = False
        self.btn_host.enabled = False
        self.btn_join.enabled = False
        self.status_msg = "正在尝试连接 127.0.0.1:8888..."
        self.status_color = TOY_COLORS["warm_orange"]
        threading.Thread(target=self._async_join_worker, daemon=True).start()

    def _async_join_worker(self):
        from game.net import GameNet
        for attempt in range(8):
            if not self.is_working:
                return
            try:
                net = GameNet(host="127.0.0.1", port=8888)
                net.join_server()
                self.net_client = net
                self.client_connected = True
                return
            except Exception:
                time.sleep(0.8)

        self.status_msg = "连接超时 (请检查对方是否已点创建主机)"
        self.status_color = TOY_COLORS["danger_red"]
        self.is_working = False
        self.btn_host.enabled = True
        self.btn_join.enabled = True

    def _go_back(self):
        self.is_working = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None
        if self.net_client:
            try:
                self.net_client.close()
            except Exception:
                pass
            self.net_client = None
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def update(self, dt):
        if self.client_connected and self.net_client:
            self.client_connected = False
            self.is_working = False
            self.status_msg = "成功连通！马上进入游戏..."
            self.status_color = TOY_COLORS["success_green"]

            if self.is_host_mode:
                from .map_select_screen import MapSelectScreen
                self.manager.switch_to(
                    MapSelectScreen, game_mode="net",
                    net_client=self.net_client, is_host=True
                )
            else:
                # 客机：进入等待界面，等主机选好地图后发 sync_game_start
                self.manager.switch_to(
                    NetClientWaitScreen, net_client=self.net_client
                )

    def draw(self, surface):
        surface.fill(TOY_COLORS["bg_cream"])
        self.panel.draw(surface)
        for w in self.widgets:
            w.draw(surface)
        font = get_font(20, bold=True, style="chinese")
        m_surf = font.render(self.status_msg, True, self.status_color)
        surface.blit(m_surf, (self.manager.WIN_W // 2 - m_surf.get_width() // 2, 550))


# ═══════════════════════════════════════════════════════════
#  客机等待界面：等待主机选好地图后发 sync_game_start
# ═══════════════════════════════════════════════════════════

class NetClientWaitScreen(BaseScreen):
    """客机等待界面：连接成功后等待主机发送 sync_game_start 消息。

    主机选好地图开局后，会通过 net_client 发送 sync_game_start 消息，
    包含 map_data 和 game_state，客机收到后同步进入 GameScreen。
    """

    def __init__(self, manager, net_client=None):
        super().__init__(manager)
        self.net_client = net_client
        self.title = ToyTitle("等待主机选地图", center_x=manager.WIN_W // 2,
                              center_y=200, font_size=48)
        self.panel = ToyPanel((manager.WIN_W // 2 - 220, 280, 440, 200))
        self.status_msg = "已连接主机，等待对方选择地图并开始游戏..."
        self.status_color = TOY_COLORS["dark_text"]
        self.btn_back = ToyButton(
            "取消等待 / 返回大厅", rect=(manager.WIN_W // 2 - 140, 520, 280, 56),
            callback=self._go_back, color=TOY_COLORS["danger_red"],
        )
        self.widgets = [self.title, self.btn_back]
        play_stagger_spawn(self, anim_dur=0.3, gap=0.08)
        # 等待动画计时器
        self._dot_timer = 0.0
        self._dot_count = 0

    def _go_back(self):
        if self.net_client:
            try:
                self.net_client.close()
            except Exception:
                pass
            self.net_client = None
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def update(self, dt):
        if not self.net_client:
            return
        # 等待动画：动态省略号
        self._dot_timer += dt
        if self._dot_timer >= 0.5:
            self._dot_timer = 0.0
            self._dot_count = (self._dot_count + 1) % 4
            dots = "." * self._dot_count
            self.status_msg = f"已连接主机，等待对方选择地图并开始游戏{dots}"

        # 非阻塞读取消息，排空所有积累包
        while True:
            msg = self.net_client.get_message(timeout=0.0)
            if not msg:
                break
            msg_type = msg.get("type")
            if msg_type == "action":
                payload = msg.get("payload", {})
                act_type = payload.get("act_type")
                if act_type == "sync_game_start":
                    # 收到主机发来的同步消息，提取 map_data 和 game_state
                    map_data = payload.get("map_data")
                    game_state = payload.get("game_state")
                    # 同步进入 GameScreen，传入 init_game_state 让客机 from_dict 覆盖
                    from .game_screen import GameScreen
                    self.manager.switch_to(
                        GameScreen,
                        map_data=map_data,
                        game_mode="net",
                        net_client=self.net_client,
                        is_host=False,
                        init_game_state=game_state,
                    )
                    return
            # 忽略其他消息类型（如 heartbeat、action 等）

    def draw(self, surface):
        surface.fill(TOY_COLORS["bg_cream"])
        self.panel.draw(surface)
        for w in self.widgets:
            w.draw(surface)
        font = get_font(20, bold=True, style="chinese")
        m_surf = font.render(self.status_msg, True, self.status_color)
        surface.blit(m_surf, (self.manager.WIN_W // 2 - m_surf.get_width() // 2, 360))