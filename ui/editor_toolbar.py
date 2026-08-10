"""
编辑器工具栏。

左侧地形拖拽工具 + 顶部操作按钮栏。
"""

import logging
from typing import Optional, Callable, List

import pygame

from .ui_const import FALLBACK_GRAY
from .widgets import (
    ToyButton, TOY_COLORS, get_font, draw_rounded_rect,
    TerrainDragTool,
)
from .drag_drop import DragDropManager
from game.constants import (
    TERRAIN_LIST, TERRAIN_COLOR, TERRAIN_DATA,
)

logger = logging.getLogger(__name__)

# ─── 左侧工具栏常量 ──────────────────────────────────────────
SIDEBAR_W = 80          # 左侧工具栏宽度
SIDEBAR_TOOL_H = 56     # 每个地形工具高度
SIDEBAR_TOOL_GAP = 6    # 工具间距
SIDEBAR_TOP = 60        # 工具栏起始Y（避开顶部按钮）


class EditorToolbar:
    """编辑器工具栏。

    包含左侧地形拖拽列表和顶部操作按钮。

    Attributes:
        terrain_tools: 地形拖拽工具列表
        drag_mgr: 拖拽管理器
        buttons: 操作按钮字典
        current_terrain: 当前选中的地形 key（用于画布点击创建节点）
    """

    def __init__(self, sidebar_w: int = SIDEBAR_W,
                 win_w: int = 1280, win_h: int = 800):
        self.sidebar_w = sidebar_w
        self.win_w = win_w
        self.win_h = win_h

        # 当前选中地形（点击地形工具时更新，画布创建节点时使用）
        self.current_terrain: str = TERRAIN_LIST[0] if TERRAIN_LIST else "normal"

        # 地形拖拽工具
        self.terrain_tools: List[TerrainDragTool] = []
        self._init_terrain_tools()

        # 拖拽管理器
        self.drag_mgr = DragDropManager()
        self._terrain_drag_key: Optional[str] = None

        # 操作按钮
        self.buttons: dict = {}
        self._init_buttons()

        # 连线模式状态
        self.wiring_mode: bool = False

        # 星星放置模式状态
        self.star_mode: bool = False

        # 回调
        self.on_new_map: Optional[Callable] = None
        self.on_save: Optional[Callable] = None
        self.on_load: Optional[Callable] = None
        self.on_eval: Optional[Callable] = None
        self.on_undo: Optional[Callable] = None
        self.on_redo: Optional[Callable] = None
        self.on_back: Optional[Callable] = None
        self.on_fit_view: Optional[Callable] = None
        self.on_clear: Optional[Callable] = None
        self.on_toggle_wiring: Optional[Callable] = None
        self.on_toggle_star_mode: Optional[Callable] = None
        # 地形选中回调：点击地形工具时触发，参数 (terrain_key)
        self.on_terrain_select: Optional[Callable[[str], None]] = None

    def _init_terrain_tools(self) -> None:
        """初始化左侧地形拖拽工具栏。"""
        self.terrain_tools = []
        y = SIDEBAR_TOP
        for ter_key in TERRAIN_LIST:
            color = TERRAIN_COLOR.get(ter_key, FALLBACK_GRAY)
            symbol = TERRAIN_DATA.get(ter_key, {}).get("name", ter_key[:2])[:2]
            name = TERRAIN_DATA.get(ter_key, {}).get("name", ter_key[:4])
            tool = TerrainDragTool(
                x=8, y=y, terrain_key=ter_key,
                color=color, symbol=symbol, name=name,
                width=self.sidebar_w - 16, height=SIDEBAR_TOOL_H,
            )
            self.terrain_tools.append(tool)
            y += SIDEBAR_TOOL_H + SIDEBAR_TOOL_GAP

    def _init_buttons(self) -> None:
        """初始化顶部操作按钮。"""
        bx = self.sidebar_w + 10
        self.buttons["new"] = ToyButton(
            "新地图", rect=(bx, 10, 90, 36),
            callback=lambda: self.on_new_map and self.on_new_map(),
            color=TOY_COLORS["secondary_cyan"], icon_type="new",
        )
        bx += 100
        self.buttons["save"] = ToyButton(
            "保存", rect=(bx, 10, 70, 36),
            callback=lambda: self.on_save and self.on_save(),
            color=TOY_COLORS["success_green"], icon_type="save",
        )
        bx += 80
        self.buttons["load"] = ToyButton(
            "加载", rect=(bx, 10, 70, 36),
            callback=lambda: self.on_load and self.on_load(),
            color=TOY_COLORS["soft_blue"], icon_type="load",
        )
        bx += 80
        self.buttons["eval"] = ToyButton(
            "评估", rect=(bx, 10, 70, 36),
            callback=lambda: self.on_eval and self.on_eval(),
            color=TOY_COLORS["primary_yellow"], icon_type="eval",
        )
        bx += 80
        self.buttons["undo"] = ToyButton(
            "撤销", rect=(bx, 10, 70, 36),
            callback=lambda: self.on_undo and self.on_undo(),
            color=TOY_COLORS["soft_purple"], icon_type="undo",
        )
        bx += 80
        self.buttons["redo"] = ToyButton(
            "重做", rect=(bx, 10, 70, 36),
            callback=lambda: self.on_redo and self.on_redo(),
            color=TOY_COLORS["soft_purple"], icon_type="redo",
        )
        bx += 80
        self.buttons["fit"] = ToyButton(
            "适配", rect=(bx, 10, 70, 36),
            callback=lambda: self.on_fit_view and self.on_fit_view(),
            color=TOY_COLORS["warm_orange"], icon_type="fit",
        )
        bx += 80
        self.buttons["clear"] = ToyButton(
            "清空", rect=(bx, 10, 70, 36),
            callback=lambda: self.on_clear and self.on_clear(),
            color=TOY_COLORS["danger_red"], icon_type="clear",
        )
        bx += 80
        self.buttons["wire"] = ToyButton(
            "连线", rect=(bx, 10, 70, 36),
            callback=lambda: self.on_toggle_wiring and self.on_toggle_wiring(),
            color=TOY_COLORS["soft_blue"], icon_type="wire",
        )
        bx += 80
        self.buttons["star"] = ToyButton(
            "星星", rect=(bx, 10, 70, 36),
            callback=lambda: self.on_toggle_star_mode and self.on_toggle_star_mode(),
            color=TOY_COLORS["primary_yellow"], icon_type="star",
        )
        # 返回按钮靠右
        self.buttons["back"] = ToyButton(
            "返回", rect=(self.win_w - 110, 10, 90, 36),
            callback=lambda: self.on_back and self.on_back(),
            color=TOY_COLORS["danger_red"], icon_type="back",
        )

    @property
    def all_widgets(self) -> list:
        """所有可交互控件（按钮）。"""
        return list(self.buttons.values())

    # ─── 拖拽地形 ────────────────────────────────────────────

    def make_terrain_drag_image(self, terrain_key: str) -> pygame.Surface:
        """创建地形拖影 Surface（使用缓存地形图标）。"""
        from .render_cache import get_cached_terrain
        w, h = 60, 60
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        # 使用缓存地形图标
        ter_surf = get_cached_terrain(terrain_key, target_size=52)
        surf.blit(ter_surf, (w // 2 - ter_surf.get_width() // 2,
                              h // 2 - ter_surf.get_height() // 2))
        # 描边
        pygame.draw.circle(surf, TOY_COLORS["dark_text"], (w // 2, h // 2), 27, 2)
        return surf

    def handle_terrain_drag(self, event) -> Optional[str]:
        """处理地形工具栏拖拽事件。

        点击地形工具时同步更新 current_terrain 并触发 on_terrain_select 回调。

        返回:
            str: 开始拖拽的地形 key
            tuple("drop", ...): 释放在工具栏自身
            None: 无事件
        """
        if event.type not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                              pygame.MOUSEMOTION):
            return None
        for tool in self.terrain_tools:
            res = tool.handle_event(event)
            if res is not None:
                if isinstance(res, str):
                    # 点击/开始拖拽 → 更新当前地形 + 触发回调
                    self.current_terrain = res
                    if self.on_terrain_select:
                        self.on_terrain_select(res)
                return res
        return None

    def start_terrain_drag(self, terrain_key: str) -> None:
        """启动地形拖拽。"""
        self._terrain_drag_key = terrain_key
        drag_img = self.make_terrain_drag_image(terrain_key)
        # 找到对应工具的 rect
        for tool in self.terrain_tools:
            if tool.terrain_key == terrain_key:
                self.drag_mgr.start_drag(terrain_key, tool.rect, drag_img)
                return
        # fallback
        self.drag_mgr.start_drag(terrain_key, pygame.Rect(0, 0, 60, 60), drag_img)

    @property
    def terrain_drag_key(self) -> Optional[str]:
        """当前拖拽中的地形 key。"""
        return self._terrain_drag_key

    @terrain_drag_key.setter
    def terrain_drag_key(self, value: Optional[str]) -> None:
        self._terrain_drag_key = value

    # ─── 绘制 ────────────────────────────────────────────────

    def draw_sidebar(self, surface: pygame.Surface) -> None:
        """绘制左侧工具栏背景和地形按钮。"""
        # 背景
        sidebar_rect = pygame.Rect(0, 0, self.sidebar_w, self.win_h)
        draw_rounded_rect(surface, (45, 45, 55), sidebar_rect, radius=0)
        # 地形按钮（当前选中地形加高亮边框）
        for tool in self.terrain_tools:
            tool.draw(surface)
            if tool.terrain_key == self.current_terrain:
                # 选中指示：金色粗边框
                pygame.draw.rect(surface, (255, 220, 0),
                                 tool.rect.inflate(4, 4), 3, border_radius=10)

    def draw_drag(self, surface: pygame.Surface,
                  target_pos_func=None) -> None:
        """绘制拖拽高亮和拖影。"""
        self.drag_mgr.draw_target_highlight(
            surface, target_pos_func=target_pos_func)
        self.drag_mgr.draw(surface)

    def draw_hints(self, surface: pygame.Surface, evaluation: dict = None) -> None:
        """绘制快捷键提示和评估分数。"""
        if self.wiring_mode:
            hints = ("[连线模式] 左键:连线 | 右键/中键:平移 | "
                     "W/ESC:退出连线 | 滚轮:缩放")
            hint_color = (100, 255, 100)
        elif self.star_mode:
            hints = ("[星星模式] 左键:放置星星 | 右键:删除星星 | "
                     "S/ESC:退出星星模式 | 滚轮:缩放")
            hint_color = (255, 220, 50)
        else:
            hints = ("左键:选中/移动 | 右键/中键:平移 | W:连线 | S:星星 | "
                     "D:删节点 | H:红HQ | J:蓝HQ | "
                     "1-9:切地形 | Ctrl+Z:撤销 | F5:保存 | F6:加载")
            hint_color = (160, 160, 170)
        font = get_font(13, style="chinese")
        hint_surf = font.render(hints, True, hint_color)
        surface.blit(hint_surf, (self.sidebar_w + 10, 52))
        # 评估分数
        if evaluation:
            total = evaluation.get("total", 0)
            color = (80, 200, 120) if total >= 60 else (255, 100, 100)
            score_font = get_font(22, bold=True, style="chinese")
            score_surf = score_font.render(f"公平性: {total}", True, color)
            surface.blit(score_surf, (self.win_w - 200, 52))

    def draw_wire_mode_indicator(self, surface: pygame.Surface) -> None:
        """绘制模式激活指示（连线/星星按钮高亮边框）。"""
        if self.wiring_mode and "wire" in self.buttons:
            btn = self.buttons["wire"]
            # 绿色粗边框表示连线模式激活
            pygame.draw.rect(surface, (100, 255, 100),
                             btn.rect.inflate(6, 6), 3, border_radius=8)
        if self.star_mode and "star" in self.buttons:
            btn = self.buttons["star"]
            # 金色粗边框表示星星模式激活
            pygame.draw.rect(surface, (255, 220, 50),
                             btn.rect.inflate(6, 6), 3, border_radius=8)

    def update_size(self, win_w: int, win_h: int) -> None:
        """更新窗口尺寸相关布局。"""
        self.win_w = win_w
        self.win_h = win_h
        # 更新返回按钮位置
        if "back" in self.buttons:
            self.buttons["back"].rect.x = win_w - 110