"""
设置界面 — 两栏无重叠布局 + 视频播放弹窗 + 样式二级弹窗 + 内置图鉴。

左栏：音频调节（音量/静音）+ 视频播放（shipin.mp4）
右栏：图鉴入口 + 图标样式选择入口
"""

import json
import logging
from pathlib import Path
import pygame

from .ui_const import FALLBACK_GRAY
from .base_screen import BaseScreen, play_stagger_spawn
from .widgets import ToyButton, ToyLabel, ToyPanel, ToyTitle, TOY_COLORS, get_font, draw_rounded_rect

from .style_cache import get_current_icon_style, set_current_icon_style, TROOP_NAME_MAPPING
from .styles_registry import get_all_styles, get_style_name
from .render_cache import refresh_troop_cache
from .asset_loader import get_troop_img_by_style, get_terrain_img
from .ui_utils import draw_alpha_rect
from game.config import is_expansion_enabled, set_expansion_enabled
from game.constants import TROOP_DATA, TERRAIN_DATA

logger = logging.getLogger(__name__)

_STYLE_BUTTON_COLORS = [
    TOY_COLORS["primary_yellow"], TOY_COLORS["soft_purple"],
    TOY_COLORS["accent_coral"], TOY_COLORS["soft_blue"], TOY_COLORS["secondary_cyan"]
]


# ═══════════════════════════════════════════════════════════
#  视频播放二级弹窗（支持播放 shipin.mp4，带遮罩与返回按钮）
# ═══════════════════════════════════════════════════════════
class VideoPlayerModal:
    """全屏遮罩视频播放剧场：安全调用 OpenCV 播放 shipin.mp4"""

    def __init__(self, manager, on_close, win_w=1280, win_h=800):
        self.manager = manager
        self.on_close = on_close
        self.win_w = win_w
        self.win_h = win_h

        pw, ph = 920, 600
        self.panel_rect = pygame.Rect((win_w - pw) // 2, (win_h - ph) // 2, pw, ph)
        self.panel = ToyPanel(self.panel_rect)

        self.btn_close = ToyButton(
            "关闭视频 / 返回设置",
            rect=(self.panel_rect.centerx - 120, self.panel_rect.bottom - 68, 240, 50),
            callback=self.close, color=TOY_COLORS["danger_red"], icon_type="back"
        )
        self.widgets = [self.btn_close]

        self.cap = None
        self.err_msg = ""
        video_paths = [
            Path("assets/video/shipin.mp4"),
            Path("shipin.mp4"),
            Path(__file__).parent.parent / "assets" / "video" / "shipin.mp4"
        ]
        try:
            import cv2
            for vp in video_paths:
                if vp.exists():
                    self.cap = cv2.VideoCapture(str(vp))
                    break
            if not self.cap or not self.cap.isOpened():
                self.err_msg = "未检测到 shipin.mp4，请将其放置于 assets/video/ 目录"
        except ImportError:
            self.err_msg = "需运行 [pip install opencv-python] 以支持 MP4 视频解码"

    def handle_event(self, event):
        for w in self.widgets:
            w.handle_event(event)

    def draw(self, surface):
        draw_alpha_rect(surface, (0, 0, 0, 180), surface.get_rect())
        self.panel.draw(surface)

        font_title = get_font(28, bold=True, style="chinese")
        ts = font_title.render("\u25B6 游戏过场宣传视频", True, TOY_COLORS["dark_text"])
        surface.blit(ts, (self.panel_rect.centerx - ts.get_width() // 2, self.panel_rect.y + 20))

        v_rect = pygame.Rect(self.panel_rect.x + 60, self.panel_rect.y + 70, 800, 430)
        pygame.draw.rect(surface, (15, 15, 20), v_rect, border_radius=12)

        if self.cap and self.cap.isOpened():
            import cv2
            ret, frame = self.cap.read()
            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame = cv2.resize(frame, (v_rect.width, v_rect.height))
                v_surf = pygame.image.frombuffer(frame.tobytes(), frame.shape[1::-1], "RGB")
                surface.blit(v_surf, v_rect.topleft)
        elif self.err_msg:
            err_font = get_font(22, style="chinese")
            es = err_font.render(self.err_msg, True, TOY_COLORS["accent_coral"])
            surface.blit(es, (v_rect.centerx - es.get_width() // 2, v_rect.centery - 15))

        for w in self.widgets:
            w.draw(surface)

    def close(self):
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
        if self.on_close:
            self.on_close()


# ═══════════════════════════════════════════════════════════
#  图标样式设置二级弹窗（防穿透遮罩 + 双滑动条支持）
# ═══════════════════════════════════════════════════════════
class StyleSelectModal:
    """二级弹窗：卡牌图标样式切换 — 左侧垂直滚动列表 + 右侧带滑动条的预览网格"""

    # ── 布局常量 ──
    _LIST_X_OFFSET = 30       # 列表区距面板左边距
    _LIST_W = 260             # 列表区宽度
    _LIST_Y_OFFSET = 70       # 列表区距面板顶边距
    _LIST_VISIBLE_H = 400     # 列表可视区高度
    _BTN_H = 52               # 每个样式按钮高度
    _BTN_GAP = 12             # 按钮间距
    _SCROLL_STEP = 40         # 每格滚轮滚动像素

    # ── 预览网格区常量 ──
    _PREVIEW_X_OFFSET = 340   # 预览区距面板左边距
    _PREVIEW_Y_OFFSET = 105   # 预览区距面板顶边距
    _PREVIEW_W = 490          # 预览区宽度
    _PREVIEW_VISIBLE_H = 375  # 预览区可视区高度

    def __init__(self, manager, on_close, win_w=1280, win_h=800):
        self.manager = manager
        self.on_close = on_close
        pw, ph = 880, 560
        self.panel_rect = pygame.Rect((win_w - pw) // 2, (win_h - ph) // 2, pw, ph)
        self.panel = ToyPanel(self.panel_rect)

        self.current_style = get_current_icon_style()
        self.style_buttons = []
        
        # 左侧列表滚动属性
        self.scroll_y = 0
        self.max_scroll = 0
        
        # 右侧预览网格滚动属性
        self.preview_scroll_y = 0
        self.preview_max_scroll = 0
        
        self._build_style_buttons()
        self._calc_preview_scroll()

        self.btn_close = ToyButton(
            "\u2713 确认并返回",
            rect=(self.panel_rect.centerx - 120, self.panel_rect.bottom - 74, 240, 52),
            callback=self.close, color=TOY_COLORS["danger_red"], icon_type="back"
        )
        self.widgets = [self.btn_close]

    @property
    def _list_rect(self):
        """列表可视裁剪区（屏幕绝对坐标）"""
        return pygame.Rect(
            self.panel_rect.x + self._LIST_X_OFFSET,
            self.panel_rect.y + self._LIST_Y_OFFSET,
            self._LIST_W,
            self._LIST_VISIBLE_H,
        )

    @property
    def _preview_rect(self):
        """预览区可视裁剪区（屏幕绝对坐标）"""
        return pygame.Rect(
            self.panel_rect.x + self._PREVIEW_X_OFFSET,
            self.panel_rect.y + self._PREVIEW_Y_OFFSET,
            self._PREVIEW_W,
            self._PREVIEW_VISIBLE_H,
        )

    def _build_style_buttons(self):
        """构建垂直排列的样式按钮并计算滚动极限"""
        self.style_buttons.clear()
        styles = get_all_styles()
        lx = self.panel_rect.x + self._LIST_X_OFFSET
        ly_start = self.panel_rect.y + self._LIST_Y_OFFSET
        bw = self._LIST_W
        for i, sid in enumerate(styles):
            color = _STYLE_BUTTON_COLORS[i % len(_STYLE_BUTTON_COLORS)]
            if sid == self.current_style:
                color = TOY_COLORS["primary_yellow"]
            btn = ToyButton(
                f"样式 {sid} \u00B7 {get_style_name(sid)}",
                rect=(lx, ly_start + i * (self._BTN_H + self._BTN_GAP), bw, self._BTN_H),
                callback=lambda s=sid: self._switch(s), color=color
            )
            btn.style_id = sid  
            self.style_buttons.append(btn)
            
        total_h = len(styles) * self._BTN_H + max(0, len(styles) - 1) * self._BTN_GAP
        self.max_scroll = max(0, total_h - self._LIST_VISIBLE_H)
        self.scroll_y = min(self.scroll_y, self.max_scroll)

    def _calc_preview_scroll(self):
        """计算右侧预览网格的滚动极限值"""
        cols = 4
        cell_h = 110
        # 计算总行数
        rows = (len(TROOP_NAME_MAPPING) + cols - 1) // cols
        total_h = rows * cell_h
        self.preview_max_scroll = max(0, total_h - self._PREVIEW_VISIBLE_H)
        self.preview_scroll_y = max(0, min(self.preview_scroll_y, self.preview_max_scroll))

    def _switch(self, sid):
        set_current_icon_style(sid)
        refresh_troop_cache()
        self.current_style = sid
        self._build_style_buttons()

    def handle_event(self, event):
        # ── 拦截滚轮事件（独立处理左侧列表与右侧网格） ──
        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            # 1. 鼠标在左侧列表内
            if self._list_rect.collidepoint(mx, my):
                self.scroll_y -= event.y * self._SCROLL_STEP
                self.scroll_y = max(0, min(self.scroll_y, self.max_scroll))
                return  
            # 2. 鼠标在右侧预览网格内
            elif self._preview_rect.collidepoint(mx, my):
                self.preview_scroll_y -= event.y * self._SCROLL_STEP
                self.preview_scroll_y = max(0, min(self.preview_scroll_y, self.preview_max_scroll))
                return  

        # ── 拦截列表区按钮点击（带滚动偏移沙盒） ──
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            mx, my = pygame.mouse.get_pos()
            if self._list_rect.collidepoint(mx, my) or event.type == pygame.MOUSEMOTION:
                for btn in self.style_buttons:
                    btn.rect.y -= self.scroll_y
                    btn.handle_event(event)
                    btn.rect.y += self.scroll_y
                if self._list_rect.collidepoint(mx, my):
                    return  

        for w in self.widgets:
            w.handle_event(event)

    def draw(self, surface):
        draw_alpha_rect(surface, (0, 0, 0, 160), surface.get_rect())
        self.panel.draw(surface)

        # 标题
        font_t = get_font(28, bold=True, style="chinese")
        ts = font_t.render("选择棋子图标外观样式", True, TOY_COLORS["dark_text"])
        surface.blit(ts, (self.panel_rect.centerx - ts.get_width() // 2, self.panel_rect.y + 20))

        # 左右区域渲染
        self._draw_style_list(surface)
        self._draw_preview(surface)

        for w in self.widgets:
            w.draw(surface)

    def _draw_style_list(self, surface):
        clip = self._list_rect
        surface.set_clip(clip)

        for btn in self.style_buttons:
            btn.rect.y -= self.scroll_y
            if getattr(btn, "style_id", None) == self.current_style:
                pygame.draw.rect(surface, TOY_COLORS["primary_yellow"],
                                 btn.rect.inflate(6, 6), border_radius=10)
            btn.draw(surface)
            btn.rect.y += self.scroll_y

        surface.set_clip(None)

        if self.max_scroll > 0:
            track_x = clip.right + 4
            track_rect = pygame.Rect(track_x, clip.y + 4, 6, clip.height - 8)
            pygame.draw.rect(surface, (215, 215, 220), track_rect, border_radius=3)
            thumb_h = max(30, int(track_rect.height * (clip.height / (clip.height + self.max_scroll))))
            thumb_y = track_rect.y + (self.scroll_y / self.max_scroll) * (track_rect.height - thumb_h)
            thumb_rect = pygame.Rect(track_x, int(thumb_y), track_rect.width, thumb_h)
            pygame.draw.rect(surface, (140, 140, 150), thumb_rect, border_radius=3)

    def _draw_preview(self, surface):
        # 当前生效提示
        hint_f = get_font(18, bold=True, style="chinese")
        hs = hint_f.render(
            f"当前生效：样式 {self.current_style} \u00B7 {get_style_name(self.current_style)}",
            True, TOY_COLORS["secondary_cyan"]
        )
        hint_x = self.panel_rect.x + self._PREVIEW_X_OFFSET
        surface.blit(hs, (hint_x, self.panel_rect.y + 70))

        clip = self._preview_rect
        surface.set_clip(clip)

        gx = clip.x
        gy = clip.y - self.preview_scroll_y
        cols = 4
        cell_w, cell_h = 120, 110
        
        for i, entry in enumerate(TROOP_NAME_MAPPING):
            cx = gx + (i % cols) * cell_w
            cy = gy + (i // cols) * cell_h
            
            # 性能优化：超出上下边框不绘制
            if cy + cell_h < clip.top or cy > clip.bottom:
                continue

            surf = get_troop_img_by_style(entry["troop_key"], self.current_style)
            if surf:
                surface.blit(pygame.transform.smoothscale(surf, (56, 56)), (cx + 4, cy))
            else:
                pygame.draw.rect(surface, FALLBACK_GRAY, (cx + 4, cy, 56, 56), border_radius=8)

            fn = get_font(13, style="chinese")
            ns = fn.render(entry.get(f"style{self.current_style}", str(entry["troop_key"])),
                           True, TOY_COLORS["dark_text"])
            surface.blit(ns, (cx + 4 + (56 - ns.get_width()) // 2, cy + 60))

        surface.set_clip(None)

        # 绘制预览区右侧的专属滑动条
        if self.preview_max_scroll > 0:
            track_x = clip.right + 4
            track_rect = pygame.Rect(track_x, clip.y + 4, 6, clip.height - 8)
            pygame.draw.rect(surface, (215, 215, 220), track_rect, border_radius=3)
            thumb_h = max(30, int(track_rect.height * (clip.height / (clip.height + self.preview_max_scroll))))
            thumb_y = track_rect.y + (self.preview_scroll_y / self.preview_max_scroll) * (track_rect.height - thumb_h)
            thumb_rect = pygame.Rect(track_x, int(thumb_y), track_rect.width, thumb_h)
            pygame.draw.rect(surface, (140, 140, 150), thumb_rect, border_radius=3)

    def close(self):
        if self.on_close:
            self.on_close()


# ═══════════════════════════════════════════════════════════
#  主设置界面（两栏布局 + 拓展包开关 + 滚动图鉴 + 模块化详情）
# ═══════════════════════════════════════════════════════════
class SettingsScreen(BaseScreen):
    """设置主界面：音频分栏 + 拓展包开关 + 图标二级窗口 + 附带滑动条的内置图鉴"""

    def __init__(self, manager):
        super().__init__(manager)
        self.mode = "settings"
        self.ency_submode = "troop"
        self.ency_selected_key = list(TROOP_DATA.keys())[0]

        # ── 图鉴列表滚动控制参数 ──
        self.ency_list_buttons = []
        self.ency_scroll_y = 0
        self.ency_max_scroll = 0

        self.active_modal = None

        self.title = ToyTitle("系统与视听设置", center_x=manager.WIN_W // 2, center_y=75, font_size=56)
        self.panel_left = ToyPanel(rect=(120, 150, 480, 460))
        self.panel_right = ToyPanel(rect=(680, 150, 480, 460))

        # ── 左栏：声音设置 + 视频播放 ──
        self.lbl_audio = ToyLabel(" 音乐与声音", (160, 180), font_size=28, color=TOY_COLORS["dark_text"])
        self.lbl_vol = ToyLabel(self._get_vol_str(), (390, 182), font_size=22, color=TOY_COLORS["secondary_cyan"])

        self.btn_mute = ToyButton("静音: 关", rect=(160, 230, 130, 46), callback=self._toggle_mute, color=TOY_COLORS["warm_orange"])
        self.btn_vol_down = ToyButton("音量 -", rect=(310, 230, 110, 46), callback=lambda: self._adj_vol(-0.1), color=TOY_COLORS["soft_blue"])
        self.btn_vol_up = ToyButton("音量 +", rect=(440, 230, 110, 46), callback=lambda: self._adj_vol(0.1), color=TOY_COLORS["soft_blue"])

        self.btn_switch_theme = ToyButton(
            self._get_theme_btn_label(), rect=(160, 298, 390, 48),
            callback=self._toggle_menu_theme, color=TOY_COLORS["secondary_cyan"]
        )

        self.btn_play_video = ToyButton(
            "▶ 播放过场视频", rect=(160, 358, 390, 52),
            callback=self._open_video_modal, color=TOY_COLORS["primary_yellow"]
        )

        # ── 右栏：游戏玩法拓展 + 美术图鉴 ──
        self.expansion_enabled = is_expansion_enabled()

        self.lbl_gameplay = ToyLabel(" 游戏玩法与拓展", (720, 180), font_size=28, color=TOY_COLORS["dark_text"])
        self.btn_toggle_exp = ToyButton(
            self._get_exp_label(), rect=(720, 230, 400, 48),
            callback=self._toggle_expansion,
            color=TOY_COLORS["success_green"] if self.expansion_enabled else TOY_COLORS["danger_red"]
        )

        self.lbl_visual = ToyLabel(" 美术与图鉴", (720, 310), font_size=28, color=TOY_COLORS["dark_text"])

        self.btn_open_style = ToyButton(
            " 卡牌外观样式", rect=(720, 360, 400, 48),
            callback=self._open_style_modal, color=TOY_COLORS["soft_purple"]
        )
        self.btn_open_ency = ToyButton(
            " 兵种地形图鉴", rect=(720, 425, 400, 48),
            callback=lambda: self._set_mode("encyclopedia"), color=TOY_COLORS["secondary_cyan"]
        )

        self.btn_back = ToyButton(
            "返回主菜单", rect=(manager.WIN_W // 2 - 130, 650, 260, 60),
            callback=self._go_back, color=TOY_COLORS["danger_red"], icon_type="back"
        )

        # 图鉴页控件
        self.panel_ency = ToyPanel(rect=(40, 110, 1200, 580))
        self.btn_ency_t = ToyButton("兵种", rect=(60, 70, 120, 40), callback=lambda: self._set_ency_sub("troop"), color=TOY_COLORS["accent_coral"])
        self.btn_ency_r = ToyButton("地形", rect=(200, 70, 120, 40), callback=lambda: self._set_ency_sub("terrain"), color=TOY_COLORS["soft_blue"])
        self.btn_ency_back = ToyButton("← 返回设置", rect=(1060, 70, 160, 40), callback=lambda: self._set_mode("settings"), color=TOY_COLORS["secondary_cyan"])

        self.status_msg = ""
        self.status_timer = 0

        self._rebuild_ency_list()
        self._rebuild_widgets()
        play_stagger_spawn(self, anim_dur=0.3, gap=0.08, overlap_ratio=0.3)

    def _get_vol_str(self) -> str:
        try:
            from game.music_player import BGM
            return "状态: [静音]" if BGM.is_muted else f"当前音量: {int(BGM.bgm_volume * 100)}%"
        except Exception:
            return "音量: 100%"

    def _toggle_mute(self):
        try:
            from game.music_player import BGM
            muted = BGM.toggle_mute()
            self.btn_mute.text = "静音: 开" if muted else "静音: 关"
            self.btn_mute.color = TOY_COLORS["danger_red"] if muted else TOY_COLORS["warm_orange"]
            self.lbl_vol.text = self._get_vol_str()
            self.lbl_vol._font = None
        except Exception:
            pass

    def _adj_vol(self, delta):
        try:
            from game.music_player import BGM
            BGM.set_volume(BGM.bgm_volume + delta)
            self.lbl_vol.text = self._get_vol_str()
            self.lbl_vol._font = None
        except Exception:
            pass

    def _get_theme_btn_label(self) -> str:
        try:
            from game.music_player import BGM
            return f"♫ 菜单BGM: {BGM.get_current_bgm_name()}"
        except Exception:
            return "♫ 菜单BGM: 默认"

    def _toggle_menu_theme(self):
        try:
            from game.music_player import BGM
            new_theme = BGM.switch_menu_bgm()
            self.btn_switch_theme.text = self._get_theme_btn_label()
            if new_theme == "menu_theme.ogg":
                self.btn_switch_theme.color = TOY_COLORS["secondary_cyan"]
            else:
                self.btn_switch_theme.color = TOY_COLORS["accent_coral"]
        except Exception as e:
            logger.warning(f"切换曲目失败: {e}")

    def _get_exp_label(self) -> str:
        return "✨ 新兵种与地形拓展包: [已开启]" if self.expansion_enabled else "✨ 新兵种与地形拓展包: [已关闭]"

    def _toggle_expansion(self):
        self.expansion_enabled = not self.expansion_enabled
        set_expansion_enabled(self.expansion_enabled)
        self.btn_toggle_exp.text = self._get_exp_label()
        self.btn_toggle_exp.color = TOY_COLORS["success_green"] if self.expansion_enabled else TOY_COLORS["danger_red"]
        if not self.expansion_enabled and self.ency_submode == "troop":
            self.ency_selected_key = "joker"
        self._rebuild_ency_list()
        self._rebuild_widgets()
        self.status_msg = "✓ 拓展包状态已更新，将在下一局对战生效"
        self.status_timer = 120

    def _open_style_modal(self):
        self.active_modal = StyleSelectModal(
            self.manager,
            on_close=lambda: setattr(self, "active_modal", None),
            win_w=self.manager.WIN_W, win_h=self.manager.WIN_H
        )

    def _open_video_modal(self):
        self.active_modal = VideoPlayerModal(
            self.manager,
            on_close=lambda: setattr(self, "active_modal", None),
            win_w=self.manager.WIN_W, win_h=self.manager.WIN_H
        )

    def _set_mode(self, mode):
        self.mode = mode
        if mode == "encyclopedia":
            self.ency_scroll_y = 0  # 切换时重置滚轮
            self._set_ency_sub("troop")
        self._rebuild_widgets()

    def _set_ency_sub(self, sub):
        self.ency_submode = sub
        self.ency_scroll_y = 0  # 切换图鉴分页时重置滚动位置
        self.ency_selected_key = list(TROOP_DATA.keys())[0] if sub == "troop" else list(TERRAIN_DATA.keys())[0]
        self._rebuild_ency_list()
        self._rebuild_widgets()

    def _rebuild_ency_list(self):
        """重新生成支持滑动的图鉴侧边栏，并计算滚动极限值"""
        self.ency_list_buttons.clear()
        all_items = list(TROOP_DATA.items()) if self.ency_submode == "troop" else list(TERRAIN_DATA.items())

        if self.ency_submode == "troop" and not self.expansion_enabled:
            all_items = [(k, v) for k, v in all_items if k == "joker" or (isinstance(k, int) and k <= 7)]

        item_h = 44
        y = 130
        for key, data in all_items:
            btn = ToyButton(
                f"{data.get('symbol', '')} {data.get('name', key)}",
                rect=(55, y, 250, 38),
                callback=lambda k=key: setattr(self, "ency_selected_key", k),
                color=TOY_COLORS["panel_bg"]
            )
            btn.ency_key = key  # 记录专属 KEY 以便绘制选中框
            self.ency_list_buttons.append(btn)
            y += item_h

        # 计算最大滑动距离 (视口高度为 540)
        visible_h = 540
        total_h = len(all_items) * item_h
        self.ency_max_scroll = max(0, total_h - visible_h)
        self.ency_scroll_y = max(0, min(self.ency_scroll_y, self.ency_max_scroll))

    def _rebuild_widgets(self):
        if self.mode == "settings":
            self.widgets = [
                self.lbl_audio, self.lbl_vol, self.btn_mute, self.btn_vol_down, self.btn_vol_up,
                self.btn_switch_theme, self.btn_play_video,
                self.lbl_gameplay, self.btn_toggle_exp,
                self.lbl_visual, self.btn_open_style, self.btn_open_ency, self.btn_back
            ]
        else:
            # 图鉴列表从主循环事件流剥离，通过手工拦截实现滚动穿透
            self.widgets = [self.btn_ency_t, self.btn_ency_r, self.btn_ency_back]

    def _go_back(self):
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def update(self, dt):
        self.title.update(dt)
        if self.status_timer > 0:
            self.status_timer -= 1
    def handle_event(self, event):
        if self.active_modal:
            self.active_modal.handle_event(event)
            return

        # ── 拦截图鉴列表滚动及点击事件 ──
        if self.mode == "encyclopedia":
            # 左侧滑动感应区 (X:40~330, Y:110~690)
            list_rect = pygame.Rect(40, 110, 290, 580)
            mx, my = pygame.mouse.get_pos()

            # 处理滚轮
            if event.type == pygame.MOUSEWHEEL and list_rect.collidepoint(mx, my):
                self.ency_scroll_y -= event.y * 36  # 每格滚 36 像素
                self.ency_scroll_y = max(0, min(self.ency_scroll_y, self.ency_max_scroll))
                return

            # 手工处理滑动列表内按钮点击与悬浮，带安全沙盒防越界触发
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                if event.type == pygame.MOUSEMOTION or list_rect.collidepoint(mx, my):
                    for btn in self.ency_list_buttons:
                        btn.rect.y -= self.ency_scroll_y  # 临时应用偏移参与碰撞检测
                        btn.handle_event(event)
                        btn.rect.y += self.ency_scroll_y  # 恢复坐标

        super().handle_event(event)
        self.title.handle_event(event)

    def draw(self, surface):
        surface.fill(TOY_COLORS["bg_cream"])
        self.title.draw(surface)

        if self.mode == "settings":
            self.panel_left.draw(surface)
            self.panel_right.draw(surface)

        else:
            self.panel_ency.draw(surface)
            self._draw_ency_list(surface)    # 滑动列表渲染
            self._draw_ency_detail(surface)  # 模块化详情渲染

        for w in self.widgets:
            w.draw(surface)

        if self.status_timer > 0 and self.status_msg:
            font = get_font(20, style="chinese")
            txt = font.render(self.status_msg, True, TOY_COLORS["success_green"])
            surface.blit(txt, (460, 600))

        if self.active_modal:
            self.active_modal.draw(surface)

    def _draw_ency_list(self, surface):
        """带裁剪框与滑动条的图鉴左侧列表绘制"""
        # 裁剪窗口：只显示此范围内的列表内容
        clip_rect = pygame.Rect(45, 120, 290, 540)
        surface.set_clip(clip_rect)

        for btn in self.ency_list_buttons:
            btn.rect.y -= self.ency_scroll_y
            # 绘制当前选中的高亮金边
            if getattr(btn, "ency_key", None) == self.ency_selected_key:
                pygame.draw.rect(surface, TOY_COLORS["primary_yellow"], btn.rect.inflate(6, 6), border_radius=10)
            btn.draw(surface)
            btn.rect.y += self.ency_scroll_y

        surface.set_clip(None)

        # 绘制优雅圆润的内嵌式细长滑动条
        if self.ency_max_scroll > 0:
            track_rect = pygame.Rect(318, 130, 6, 520)
            # 滑动槽底色
            pygame.draw.rect(surface, (215, 215, 220), track_rect, border_radius=3)
            # 滑块高度与位置计算
            thumb_h = max(36, int(520 * (520 / (520 + self.ency_max_scroll))))
            thumb_y = track_rect.y + (self.ency_scroll_y / self.ency_max_scroll) * (track_rect.height - thumb_h)
            thumb_rect = pygame.Rect(track_rect.x, int(thumb_y), track_rect.width, thumb_h)
            # 胶囊滑块本体
            pygame.draw.rect(surface, (140, 140, 150), thumb_rect, border_radius=3)

    def _draw_ency_detail(self, surface):
        """结构重排：图标居左展示数据，右侧宽广留白方便后续属性面板扩充"""
        font_title = get_font(38, bold=True, style="chinese")
        font_stats = get_font(20, bold=True, style="chinese")
        font_desc = get_font(20, style="chinese")

        # 整体向右推移，为左侧滚动条与呼吸区留出近 400px，自身则拥有 800+ 像素宽广画布
        base_x, base_y = 380, 150
        data = (TROOP_DATA if self.ency_submode == "troop" else TERRAIN_DATA).get(self.ency_selected_key)
        if not data:
            return

        # ── 1. 顶部：大尺寸主图标绘制 ──
        img = (get_troop_img_by_style(self.ency_selected_key, get_current_icon_style())
               if self.ency_submode == "troop" else get_terrain_img(self.ency_selected_key))
        if img:
            surface.blit(pygame.transform.smoothscale(img, (96, 96)), (base_x, base_y))
            txt_x = base_x + 120
        else:
            txt_x = base_x

        # ── 2. 标题区（带属性前缀框，方便未来加特殊TAG） ──
        title = f"{data.get('symbol', '')} {data.get('name', self.ency_selected_key)}"
        surface.blit(font_title.render(title, True, TOY_COLORS["dark_text"]), (txt_x, base_y + 12))

        # 预留属性展示槽 (例如：基础战力 / 属性标签)
        if self.ency_submode == "troop":
            num_val = data.get("num")
            stat_str = f"基础战力: {num_val if num_val is not None else 'J (万能)'}"
            stat_surf = font_stats.render(stat_str, True, TOY_COLORS["secondary_cyan"])
            surface.blit(stat_surf, (txt_x, base_y + 60))
        else:
            stat_str = "场地属性: 战局环境"
            stat_surf = font_stats.render(stat_str, True, TOY_COLORS["soft_purple"])
            surface.blit(stat_surf, (txt_x, base_y + 60))

        # ── 3. 华丽分割线（分隔基本属性和深度背景长文） ──
        line_y = base_y + 120
        pygame.draw.line(surface, (210, 210, 215), (base_x, line_y), (base_x + 780, line_y), 2)

        # ── 4. 文本长篇陈述区（支持自动换行切分防止溢出） ──
        text_y = line_y + 30
        desc_text = data.get("desc", "")
        # 为了不越界，长串文字简单按 38 字符宽度切分折行渲染
        max_chars = 38
        lines = []
        for raw_line in desc_text.split('\n'):
            for i in range(0, len(raw_line), max_chars):
                lines.append(raw_line[i:i + max_chars])

        for line in lines:
            surface.blit(font_desc.render(line, True, (80, 80, 85)), (base_x, text_y))
            text_y += 34