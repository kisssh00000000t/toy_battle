"""
弹窗组件库：模式选择、游戏结算、暂停菜单等二级界面。

基于 UIManager 弹窗栈协议（handle_event / draw / close），
零侵入地增加二级菜单和游戏结束菜单。

组件：
    ModeSelectModal: 对战模式选择弹窗（单人AI / 本地同屏 / 局域网联机）
    GameOverModal: 游戏结算中心（立即回放 / 保存战报 / 再来一局 / 主菜单）
    PauseModal: 暂停菜单（继续游戏 / 导出残局 / 返回主菜单）
"""

import time
from pathlib import Path

import pygame

from .widgets import ToyButton, ToyPanel, TOY_COLORS, get_font
from .ui_utils import draw_alpha_rect


class ModeSelectModal:
    """二级界面：对战模式选择弹窗。

    在主菜单点击"开始对战"时由 ui_mgr.push_modal() 弹出。
    提供三种对战模式：单人 VS AI、本地同屏、局域网联机。

    协议：handle_event(event) / draw(surface) / close()
    """

    def __init__(self, manager, win_w=1280, win_h=800):
        self.manager = manager
        self.win_w = win_w
        self.win_h = win_h

        # 弹窗尺寸与居中
        pw, ph = 480, 420
        self.panel_rect = pygame.Rect((win_w - pw) // 2, (win_h - ph) // 2, pw, ph)
        self.panel = ToyPanel(self.panel_rect)

        # 字体
        self.title_font = get_font(32, bold=True, style="chinese")

        # 功能按键
        bx = self.panel_rect.x + 60
        by = self.panel_rect.y + 80
        self.btn_ai = ToyButton(
            "单人 VS AI", rect=(bx, by, 360, 60),
            callback=self._start_ai_game,
            color=TOY_COLORS["secondary_cyan"], icon_type="play"
        )
        self.btn_local = ToyButton(
            "本地同屏对战", rect=(bx, by + 80, 360, 60),
            callback=self._start_local_game,
            color=TOY_COLORS["primary_yellow"], icon_type="play"
        )
        self.btn_net = ToyButton(
            "局域网联网对战", rect=(bx, by + 160, 360, 60),
            callback=self._start_net_game,
            color=TOY_COLORS["soft_blue"], icon_type="map"
        )
        self.btn_close = ToyButton(
            "关闭", rect=(bx + 90, by + 250, 180, 50),
            callback=self.close,
            color=TOY_COLORS["danger_red"]
        )
        self.widgets = [self.btn_ai, self.btn_local, self.btn_net, self.btn_close]

    def _start_ai_game(self):
        """切换到地图选择界面（AI模式）。"""
        from .map_select_screen import MapSelectScreen
        self.close()
        self.manager.switch_to(MapSelectScreen, game_mode="ai")

    def _start_local_game(self):
        """切换到地图选择界面（本地对战模式）。"""
        from .map_select_screen import MapSelectScreen
        self.close()
        self.manager.switch_to(MapSelectScreen, game_mode="local")

    def _start_net_game(self):
        """切换到局域网大厅界面。"""
        from .net_lobby_screen import NetLobbyScreen
        self.close()
        self.manager.switch_to(NetLobbyScreen)

    def handle_event(self, event):
        """处理弹窗内按钮事件。"""
        for w in self.widgets:
            w.handle_event(event)

    def draw(self, surface):
        """绘制弹窗：半透明暗底 + 卡片面板 + 标题 + 按钮。"""
        # 半透明黑色暗底
        draw_alpha_rect(surface, (0, 0, 0, 140), surface.get_rect())
        # 卡片面板
        self.panel.draw(surface)
        # 标题
        t_surf = self.title_font.render("选择游戏对战模式", True, TOY_COLORS["dark_text"])
        surface.blit(t_surf, (self.panel_rect.centerx - t_surf.get_width() // 2,
                              self.panel_rect.y + 24))
        # 按钮
        for w in self.widgets:
            w.draw(surface)

    def close(self):
        """关闭弹窗，从 UIManager 弹窗栈弹出。"""
        screen = self.manager.current_screen
        if screen and hasattr(screen, "ui_mgr"):
            screen.ui_mgr.pop_modal()


class GameOverModal:
    """游戏结算中心弹窗。

    替代简单的"点击返回菜单"文字，提供互动操作中心：
    - 立即回放对局（ReplayEngine 内存回放）
    - 保存战报到本地（export_replay JSON）
    - 再来一局（同配置重开）
    - 返回主菜单

    协议：handle_event(event) / draw(surface) / close()
    """

    def __init__(self, manager, game_state, map_source="custom",
                 game_mode="local", win_w=1280, win_h=800):
        self.manager = manager
        self.game = game_state
        self.map_source = map_source
        self.game_mode = game_mode
        self.win_w = win_w
        self.win_h = win_h

        pw, ph = 500, 440
        self.panel_rect = pygame.Rect((win_w - pw) // 2, (win_h - ph) // 2, pw, ph)
        self.panel = ToyPanel(self.panel_rect)

        self.title_font = get_font(44, bold=True, style="chinese")
        self.msg_font = get_font(18, style="chinese")
        self.status_msg = "\u2713 战报已自动存档"

        # 功能按钮
        bx = self.panel_rect.x + 70
        by = self.panel_rect.y + 110
        self.btn_replay = ToyButton(
            "立即回放对局", rect=(bx, by, 360, 56),
            callback=self._do_instant_replay,
            color=TOY_COLORS["primary_yellow"], icon_type="play"
        )
        self.btn_save = ToyButton(
            "保存战报到本地", rect=(bx, by + 70, 360, 56),
            callback=self._do_save_replay,
            color=TOY_COLORS["success_green"], icon_type="save"
        )
        self.btn_restart = ToyButton(
            "再来一局", rect=(bx, by + 140, 170, 56),
            callback=self._do_rematch,
            color=TOY_COLORS["secondary_cyan"]
        )
        self.btn_menu = ToyButton(
            "主菜单", rect=(bx + 190, by + 140, 170, 56),
            callback=self._do_to_menu,
            color=TOY_COLORS["accent_coral"]
        )
        self.widgets = [self.btn_replay, self.btn_save, self.btn_restart, self.btn_menu]

    def _do_instant_replay(self):
        """进入战报回放系统（内存 action_log 驱动）。"""
        try:
            from .replay_screen import ReplayScreen
            self.manager.switch_to(ReplayScreen,
                                   action_log=self.game.action_log,
                                   map_source=self.map_source)
        except ImportError:
            self.status_msg = "回放界面尚未实现，敬请期待"

    def _do_save_replay(self):
        """保存为时间戳格式 JSON 战报文件。"""
        from game.replay import export_replay
        t_str = time.strftime("%Y%m%d_%H%M%S")
        winner_str = self.game.winner or "draw"
        filename = f"replay_{t_str}_{winner_str}.json"
        save_path = Path("replays") / filename
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            export_replay(self.game, self.map_source, save_path)
            self.status_msg = f"战报已保存: replays/{filename}"
        except Exception as e:
            self.status_msg = f"保存失败: {e}"

    def _do_rematch(self):
        """用原有地图和参数马上开启一场新对弈。"""
        from .game_screen import GameScreen
        self.manager.switch_to(GameScreen, map_data=None, game_mode=self.game_mode)

    def _do_to_menu(self):
        """返回主菜单。"""
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def handle_event(self, event):
        """处理弹窗内按钮事件。"""
        for w in self.widgets:
            w.handle_event(event)

    def draw(self, surface):
        """绘制结算弹窗。"""
        # 半透明暗底
        draw_alpha_rect(surface, (0, 0, 0, 160), surface.get_rect())
        # 卡片面板
        self.panel.draw(surface)

        # 胜负标题
        winner = self.game.winner or "平局"
        col = TOY_COLORS["accent_coral"] if winner == "red" else TOY_COLORS["soft_blue"]
        t_surf = self.title_font.render(f"{winner.upper()} 获胜！", True, col)
        surface.blit(t_surf, (self.panel_rect.centerx - t_surf.get_width() // 2,
                              self.panel_rect.y + 30))

        # 星星比分
        sub_font = get_font(22, style="chinese")
        red_s = self.game.red.star_points
        blue_s = self.game.blue.star_points
        score_txt = sub_font.render(f"红 {red_s} : {blue_s} 蓝", True, TOY_COLORS["dark_text"])
        surface.blit(score_txt, (self.panel_rect.centerx - score_txt.get_width() // 2,
                                 self.panel_rect.y + 80))

        # 按钮
        for w in self.widgets:
            w.draw(surface)

        # 状态提示
        if self.status_msg:
            s_surf = self.msg_font.render(self.status_msg, True, TOY_COLORS["success_green"])
            surface.blit(s_surf, (self.panel_rect.centerx - s_surf.get_width() // 2,
                                  self.panel_rect.bottom - 40))

    def close(self):
        """结算弹窗不允许通过 ESC 强行关闭（防止空白画布）。"""
        pass


class PauseModal:
    """暂停菜单弹窗。

    ESC 键触发，提供：
    - 继续游戏（关闭弹窗）
    - 导出残局快照（self.game.to_dict() 保存 JSON）
    - 返回主菜单

    协议：handle_event(event) / draw(surface) / close()
    """

    def __init__(self, manager, game_state, map_source="custom",
                 win_w=1280, win_h=800):
        self.manager = manager
        self.game = game_state
        self.map_source = map_source
        self.win_w = win_w
        self.win_h = win_h

        pw, ph = 400, 340
        self.panel_rect = pygame.Rect((win_w - pw) // 2, (win_h - ph) // 2, pw, ph)
        self.panel = ToyPanel(self.panel_rect)

        self.title_font = get_font(32, bold=True, style="chinese")
        self.msg_font = get_font(16, style="chinese")
        self.status_msg = "\u2713 战报已自动存档"

        # 功能按钮
        bx = self.panel_rect.x + 50
        by = self.panel_rect.y + 80
        self.btn_resume = ToyButton(
            "继续游戏", rect=(bx, by, 300, 56),
            callback=self.close,
            color=TOY_COLORS["success_green"], icon_type="play"
        )
        self.btn_export = ToyButton(
            "导出残局快照", rect=(bx, by + 70, 300, 56),
            callback=self._do_export_snapshot,
            color=TOY_COLORS["primary_yellow"], icon_type="save"
        )
        self.btn_quit = ToyButton(
            "返回主菜单", rect=(bx, by + 140, 300, 56),
            callback=self._do_quit_to_menu,
            color=TOY_COLORS["danger_red"]
        )
        self.widgets = [self.btn_resume, self.btn_export, self.btn_quit]

    def _do_export_snapshot(self):
        """导出当前局势快照为 JSON 文件。"""
        import json
        t_str = time.strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_{t_str}.json"
        save_path = Path("replays") / filename
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = self.game.to_dict()
            snapshot["map_source"] = self.map_source
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            self.status_msg = f"快照已保存: replays/{filename}"
        except Exception as e:
            self.status_msg = f"保存失败: {e}"

    def _do_quit_to_menu(self):
        """返回主菜单。"""
        self.close()
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def handle_event(self, event):
        """处理弹窗内按钮事件。"""
        for w in self.widgets:
            w.handle_event(event)

    def draw(self, surface):
        """绘制暂停弹窗。"""
        # 半透明暗底
        draw_alpha_rect(surface, (0, 0, 0, 140), surface.get_rect())
        # 卡片面板
        self.panel.draw(surface)
        # 标题
        t_surf = self.title_font.render("游戏暂停", True, TOY_COLORS["dark_text"])
        surface.blit(t_surf, (self.panel_rect.centerx - t_surf.get_width() // 2,
                              self.panel_rect.y + 24))
        # 按钮
        for w in self.widgets:
            w.draw(surface)
        # 状态提示
        if self.status_msg:
            s_surf = self.msg_font.render(self.status_msg, True, TOY_COLORS["success_green"])
            surface.blit(s_surf, (self.panel_rect.centerx - s_surf.get_width() // 2,
                                  self.panel_rect.bottom - 36))

    def close(self):
        """关闭暂停弹窗，恢复游戏。"""
        screen = self.manager.current_screen
        if screen and hasattr(screen, "ui_mgr"):
            screen.ui_mgr.pop_modal()