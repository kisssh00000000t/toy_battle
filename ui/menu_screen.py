"""
主菜单界面。

提供：开始对战、创意工坊、战报大厅、设置四个入口。
包含漂浮装饰动画（星星/云朵上下浮动）。
"""

import logging

import pygame

from .base_screen import BaseScreen, play_stagger_spawn
from .widgets import ToyButton, ToyLabel, ToyTitle, TOY_COLORS, get_font
from .ui_manager import UIManager
from .camera import Camera


logger = logging.getLogger(__name__)


class _FloatingDeco:
    """漂浮装饰元素，循环上下浮动 + 旋转 + 脉动缩放。"""

    def __init__(self, deco_type, x, y, size, color, amplitude, period,
                 rot_speed=20, pulse_amp=0.12, pulse_period=2.0):
        self.deco_type = deco_type  # "star_filled" or "star_hollow"
        self.x = x
        self.base_y = y
        self.y = y
        self.size = size
        self.color = color
        self.amplitude = amplitude
        self.period = period  # 秒
        self.rot_speed = rot_speed      # 旋转速度（度/秒）
        self.pulse_amp = pulse_amp      # 脉动缩放幅度（0~1）
        self.pulse_period = pulse_period  # 脉动周期（秒）
        self._elapsed = 0.0
        self.alpha = 255
        self._angle = 0.0
        self._scale = 1.0

    def update(self, dt):
        self._elapsed += dt
        # 正弦波上下浮动
        self.y = self.base_y - self.amplitude * (
            0.5 - 0.5 * pygame.math.Vector2(1, 0).rotate(
                self._elapsed / self.period * 360
            ).y
        )
        # 缓慢旋转
        self._angle = (self._elapsed * self.rot_speed) % 360
        # 脉动缩放
        self._scale = 1.0 + self.pulse_amp * (
            0.5 - 0.5 * pygame.math.Vector2(1, 0).rotate(
                self._elapsed / self.pulse_period * 360
            ).y
        )

    def draw(self, surface):
        from .render_cache import get_cached_star
        # 所有星星统一使用 star_red（红色五角星）
        star_size = self.size // 2
        star_surf = get_cached_star("red", star_size)
        # 脉动缩放
        if abs(self._scale - 1.0) > 0.005:
            new_w = max(4, int(star_surf.get_width() * self._scale))
            new_h = max(4, int(star_surf.get_height() * self._scale))
            star_surf = pygame.transform.smoothscale(star_surf, (new_w, new_h))
        # 旋转
        if abs(self._angle) > 0.5:
            star_surf = pygame.transform.rotate(star_surf, self._angle)
        # 设置alpha透明度
        if self.alpha < 255:
            star_surf = star_surf.copy()
            star_surf.set_alpha(int(self.alpha))
        # 居中绘制（旋转后尺寸变化，需偏移）
        blit_x = int(self.x) - star_surf.get_width() // 2
        blit_y = int(self.y) - star_surf.get_height() // 2
        surface.blit(star_surf, (blit_x, blit_y))


class MenuScreen(BaseScreen):
    """主菜单界面。"""

    def __init__(self, manager):
        super().__init__(manager)
        # UI 管理器（弹窗栈支持）
        self.ui_mgr = UIManager(Camera(self.manager.WIN_W, self.manager.WIN_H))
        # 标题（ToyTitle 带漂浮动效+星星装饰）
        self.title = ToyTitle(
            "玩具大乱斗", center_x=640, center_y=140,
            font_size=72, base_color=TOY_COLORS["accent_coral"]
        )
        self.subtitle = ToyLabel(
            "TroopWar", (500, 200), font_size=28, color=TOY_COLORS["dark_text"]
        )
        # 功能按钮
        self.btn_play = ToyButton(
            "开始对战", rect=(460, 260, 360, 70), callback=self._show_mode_select,
            icon_type="play"
        )
        self.btn_editor = ToyButton(
            "创意工坊", rect=(460, 350, 360, 70), callback=self.goto_workshop,
            color=TOY_COLORS["secondary_cyan"], icon_type="edit"
        )
        self.btn_replays = ToyButton(
            "战报大厅", rect=(460, 440, 360, 70), callback=self.goto_replays,
            color=TOY_COLORS["soft_blue"], icon_type="map"
        )
        self.btn_settings = ToyButton(
            "设置", rect=(460, 530, 360, 70), callback=self.goto_settings,
            color=TOY_COLORS["soft_purple"], icon_type="gear"
        )
        # 状态提示
        self.status_msg = ""
        self.status_timer = 0

        # 漂浮装饰
        self.decorations = [
            _FloatingDeco("star_filled", 80, 120, 48, TOY_COLORS["primary_yellow"], 15, 3.0),
            _FloatingDeco("star_hollow", 1150, 80, 60, TOY_COLORS["secondary_cyan"], 12, 3.5),
            _FloatingDeco("star_filled", 180, 500, 40, TOY_COLORS["accent_coral"], 10, 2.8),
            _FloatingDeco("star_hollow", 1050, 450, 44, TOY_COLORS["soft_blue"], 14, 4.0),
            _FloatingDeco("star_filled", 300, 650, 36, TOY_COLORS["success_green"], 8, 3.2),
        ]

        self.widgets = [
            self.title, self.subtitle,
            self.btn_play, self.btn_editor, self.btn_replays,
            self.btn_settings,
        ]

        # 交错入场动画
        play_stagger_spawn(self, anim_dur=0.4, gap=0.1, overlap_ratio=0.4)

        # 引入音乐播放器并开启自动播放
        try:
            from game.music_player import BGM
            BGM.play_menu_bgm()
        except Exception as e:
            logger.warning(f"BGM 自动启动失败: {e}")

    def goto_map_select(self):
        from .map_select_screen import MapSelectScreen
        self.manager.switch_to(MapSelectScreen)

    def _show_mode_select(self):
        """弹出对战模式选择弹窗。"""
        from .modals import ModeSelectModal
        modal = ModeSelectModal(
            self.manager,
            win_w=self.manager.WIN_W, win_h=self.manager.WIN_H,
        )
        self.ui_mgr.push_modal(modal)

    def goto_workshop(self):
        """跳转创意工坊二级界面。"""
        from .workshop_screen import WorkshopScreen
        self.manager.switch_to(WorkshopScreen)

    def goto_replays(self):
        """跳转战报大厅二级界面。"""
        from .replay_select_screen import ReplaySelectScreen
        self.manager.switch_to(ReplaySelectScreen)

    def goto_settings(self):
        from .settings_screen import SettingsScreen
        self.manager.switch_to(SettingsScreen)

    def update(self, dt):
        if self.status_timer > 0:
            self.status_timer -= 1
        # 更新漂浮装饰
        for deco in self.decorations:
            deco.update(dt)
        # 更新 ToyTitle 漂浮动效
        self.title.update(dt)
    def handle_event(self, event):
        """修复层级穿透：如果存在弹窗，先拦截且禁止往下派发给一级的 super().handle_event！"""
        if self.ui_mgr.has_modal:
            self.ui_mgr.handle_event(event)
            return  # 核心：必须 return 阻断，绝对禁止传给一级的 btn_play / btn_settings！
        super().handle_event(event)
        self.title.handle_event(event)

    def draw(self, surface):
        super().draw(surface)
        # 漂浮装饰
        for deco in self.decorations:
            deco.draw(surface)
        # 弹窗绘制（最顶层）
        self.ui_mgr.draw_modals(surface)
        # 状态提示
        if self.status_timer > 0 and self.status_msg:
            font = get_font(20, style="chinese")
            txt = font.render(self.status_msg, True, TOY_COLORS["success_green"])
            surface.blit(txt, (460, 620))