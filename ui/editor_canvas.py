"""
编辑器画布组件。

负责地图的可视化渲染和鼠标交互：
- 画布平移（右键拖拽 / 中键拖拽）
- 画布缩放（滚轮）
- 节点选中、拖拽移动
- 连线模式（左键连线，右键/中键纯平移）
- 节点/边的绘制

交互状态机：
- wiring_mode=False（默认）: 左键选中/移动节点，右键/中键平移
- wiring_mode=True（连线模式）: 左键连线，右键/中键平移
"""

import math
import logging
from typing import Optional, Callable, Tuple

import pygame

from .editor_model import EditorModel
from .ui_const import FALLBACK_GRAY
from .ui_utils import draw_tooltip
from .widgets import draw_rounded_rect, TOY_COLORS, get_font
from game.constants import (
    TERRAIN_COLOR, EDITOR_NODE_RADIUS,
    TILE_ROUND_RADIUS, TILE_PADDING,
)

logger = logging.getLogger(__name__)

# 缩放限制
MIN_SCALE = 0.3
MAX_SCALE = 3.0
ZOOM_STEP = 0.1

# 拖拽阈值（像素）：鼠标移动超过此距离才视为拖拽，否则为点击
DRAG_THRESHOLD = 5


class EditorCanvas:
    """编辑器画布组件。

    管理视图变换（offset/scale）和画布区域内的鼠标交互，
    将节点/边的绘制委托给自身 draw 方法。

    Attributes:
        model: EditorModel 数据引用
        offset_x, offset_y: 画布平移偏移（屏幕像素）
        scale: 画布缩放倍率
        selected_node: 当前选中节点 ID
        hover_node: 鼠标悬停节点 ID
        dragging_node: 正在拖拽移动的节点 ID
        line_start_nid: 连线起点节点 ID
        is_drawing_line: 是否正在绘制连线
        wiring_mode: 是否处于连线模式
    """

    def __init__(self, model: EditorModel,
                 area_x: int = 0, area_y: int = 0,
                 area_w: int = 0, area_h: int = 0):
        self.model = model

        # 画布区域（屏幕坐标，避开工具栏和按钮栏）
        self.area_x = area_x
        self.area_y = area_y
        self.area_w = area_w
        self.area_h = area_h

        # 视图变换
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.scale = 1.0

        # 交互状态
        self.selected_node: Optional[int] = None
        self.hover_node: Optional[int] = None
        self.dragging_node: Optional[int] = None
        self.line_start_nid: Optional[int] = None
        self.is_drawing_line: bool = False

        # 连线模式开关
        self.wiring_mode: bool = False

        # 星星放置模式开关
        self.star_mode: bool = False

        # 拖拽状态机：区分点击 vs 拖拽
        self._drag_pending: bool = False      # 左键按下但尚未超过阈值
        self._drag_start_pos: Tuple[int, int] = (0, 0)  # 按下时的屏幕坐标
        self._drag_moved: bool = False        # 是否已超过阈值（真正拖拽）

        # 右键/中键平移状态
        self._panning = False
        self._pan_start = (0, 0)
        self._pan_offset_start = (0.0, 0.0)

        # 回调：连线完成时通知 EditorScreen
        self.on_edge_added: Optional[Callable[[int, int], None]] = None
        # 回调：节点被拖拽移动时通知（用于撤销）
        self.on_node_drag_start: Optional[Callable[[], None]] = None
        # 回调：左键点击空白画布时通知（用于创建节点），参数 (wx, wy)
        self.on_empty_click: Optional[Callable[[float, float], None]] = None
        # 回调：连线模式切换时通知
        self.on_wiring_mode_changed: Optional[Callable[[bool], None]] = None
        # 回调：星星模式切换时通知
        self.on_star_mode_changed: Optional[Callable[[bool], None]] = None
        # 回调：星星左键放置 (wx, wy)
        self.on_star_place: Optional[Callable[[float, float], None]] = None
        # 回调：星星右键删除 (wx, wy)
        self.on_star_remove: Optional[Callable[[float, float], None]] = None

    # ─── 坐标变换 ────────────────────────────────────────────

    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        """世界坐标 → 屏幕坐标。"""
        sx = int(wx * self.scale + self.offset_x)
        sy = int(wy * self.scale + self.offset_y)
        return (sx, sy)

    def screen_to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        """屏幕坐标 → 世界坐标。"""
        wx = (sx - self.offset_x) / self.scale
        wy = (sy - self.offset_y) / self.scale
        return (wx, wy)

    def scaled_radius(self, world_radius: float) -> int:
        """世界半径 → 屏幕半径（最小 1）。"""
        return max(1, int(world_radius * self.scale))

    def scaled_click_radius(self, world_radius: float) -> float:
        """屏幕点击判定半径（反算，保持世界空间判定一致）。"""
        return world_radius / self.scale + 5 / self.scale

    # ─── 画布区域判定 ────────────────────────────────────────

    def _in_canvas(self, sx: int, sy: int) -> bool:
        """屏幕坐标是否在画布区域内。"""
        return (self.area_x <= sx < self.area_x + self.area_w and
                self.area_y <= sy < self.area_y + self.area_h)

    def update_area(self, x: int, y: int, w: int, h: int) -> None:
        """更新画布区域。"""
        self.area_x = x
        self.area_y = y
        self.area_w = w
        self.area_h = h

    # ─── 自动适配 ────────────────────────────────────────────

    def fit_to_view(self) -> None:
        """自动缩放和平移，使所有节点适配画布区域。"""
        if not self.model.nodes:
            self.offset_x = self.area_x + self.area_w / 2
            self.offset_y = self.area_y + self.area_h / 2
            self.scale = 1.0
            return

        # 计算包围盒
        pad = EDITOR_NODE_RADIUS + 8
        xs = [nd["x"] for nd in self.model.nodes.values()]
        ys = [nd["y"] for nd in self.model.nodes.values()]
        min_x, max_x = min(xs) - pad, max(xs) + pad
        min_y, max_y = min(ys) - pad, max(ys) + pad
        world_w = max_x - min_x
        world_h = max_y - min_y

        if world_w < 1 or world_h < 1:
            self.scale = 1.0
        else:
            scale_x = self.area_w * 0.9 / world_w
            scale_y = self.area_h * 0.9 / world_h
            self.scale = max(MIN_SCALE, min(MAX_SCALE, min(scale_x, scale_y)))

        # 居中偏移
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        self.offset_x = self.area_x + self.area_w / 2 - cx * self.scale
        self.offset_y = self.area_y + self.area_h / 2 - cy * self.scale

    # ─── 节点查找 ────────────────────────────────────────────

    def find_node_at_screen(self, sx: int, sy: int) -> Optional[int]:
        """在屏幕坐标处查找节点。"""
        wx, wy = self.screen_to_world(sx, sy)
        radius = self.scaled_click_radius(EDITOR_NODE_RADIUS)
        return self.model.find_node_at(wx, wy, radius)

    # ─── 连线模式切换 ────────────────────────────────────────

    def toggle_wiring_mode(self) -> bool:
        """切换连线模式，返回新模式状态。"""
        self.wiring_mode = not self.wiring_mode
        if not self.wiring_mode:
            # 退出连线模式时清空连线状态
            self.cancel_line()
        if self.on_wiring_mode_changed:
            self.on_wiring_mode_changed(self.wiring_mode)
        return self.wiring_mode

    def set_wiring_mode(self, enabled: bool) -> None:
        """设置连线模式。"""
        if self.wiring_mode != enabled:
            self.wiring_mode = enabled
            if not enabled:
                self.cancel_line()
            if self.on_wiring_mode_changed:
                self.on_wiring_mode_changed(self.wiring_mode)

    def toggle_star_mode(self) -> bool:
        """切换星星放置模式，返回新模式状态。"""
        self.star_mode = not self.star_mode
        # 进入星星模式时退出连线模式
        if self.star_mode and self.wiring_mode:
            self.set_wiring_mode(False)
        if self.on_star_mode_changed:
            self.on_star_mode_changed(self.star_mode)
        return self.star_mode

    def set_star_mode(self, enabled: bool) -> None:
        """设置星星放置模式。"""
        if self.star_mode != enabled:
            self.star_mode = enabled
            if self.star_mode and self.wiring_mode:
                self.set_wiring_mode(False)
            if self.on_star_mode_changed:
                self.on_star_mode_changed(self.star_mode)

    # ─── 事件处理 ────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理画布区域内的鼠标事件，返回是否消费事件。

        交互状态机：
        - wiring_mode=False: 左键选中/移动节点，右键/中键平移
        - wiring_mode=True:  左键连线，右键/中键平移
        """
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._on_mouse_down(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            return self._on_mouse_up(event)
        elif event.type == pygame.MOUSEMOTION:
            return self._on_mouse_motion(event)
        elif event.type == pygame.MOUSEWHEEL:
            return self._on_mouse_wheel(event)
        return False

    def _on_mouse_down(self, event) -> bool:
        mx, my = event.pos
        if not self._in_canvas(mx, my):
            return False

        # 中键：始终平移
        if event.button == 2:
            self._panning = True
            self._pan_start = (mx, my)
            self._pan_offset_start = (self.offset_x, self.offset_y)
            return True

        # 右键：始终平移（不再启动连线）
        if event.button == 3:
            if self.star_mode and self._in_canvas(mx, my):
                # ── 星星模式：右键删除星星 ──
                wx, wy = self.screen_to_world(mx, my)
                if self.on_star_remove:
                    self.on_star_remove(wx, wy)
                return True
            self._panning = True
            self._pan_start = (mx, my)
            self._pan_offset_start = (self.offset_x, self.offset_y)
            return True

        # 左键
        if event.button == 1:
            node = self.find_node_at_screen(mx, my)

            if self.wiring_mode:
                # ── 连线模式 ──
                return self._on_left_click_wiring(mx, my, node)
            elif self.star_mode:
                # ── 星星模式：左键放置星星 ──
                return self._on_left_click_star(mx, my)
            else:
                # ── 普通模式 ──
                return self._on_left_click_normal(mx, my, node)

        return False

    def _on_left_click_wiring(self, mx: int, my: int,
                               node: Optional[int]) -> bool:
        """连线模式下左键点击处理。"""
        if self.is_drawing_line and self.line_start_nid is not None:
            # 已有连线起点
            if node is not None and node != self.line_start_nid:
                # 点击另一个节点 → 完成连线
                if self.on_edge_added:
                    self.on_edge_added(self.line_start_nid, node)
                # 连线起点保持，支持连续连线
                self.line_start_nid = node
            elif node == self.line_start_nid:
                # 点击自身 → 取消连线
                self.cancel_line()
            else:
                # 点击空白 → 取消连线
                self.cancel_line()
        else:
            # 无连线起点
            if node is not None:
                # 点击节点 → 设为连线起点
                self.line_start_nid = node
                self.is_drawing_line = True
                self.selected_node = node
            # 点击空白 → 无操作（不创建节点）
        return True

    def _on_left_click_normal(self, mx: int, my: int,
                               node: Optional[int]) -> bool:
        """普通模式下左键点击处理（选中+拖拽阈值）。"""
        if node is not None:
            # 点击节点 → 选中 + 进入拖拽待决状态
            self.selected_node = node
            self._drag_pending = True
            self._drag_start_pos = (mx, my)
            self._drag_moved = False
            self.dragging_node = node
        else:
            # 点击空白 → 取消选中 + 通知创建节点
            self.selected_node = None
            if self.on_empty_click:
                wx, wy = self.screen_to_world(mx, my)
                self.on_empty_click(wx, wy)
        return True

    def _on_left_click_star(self, mx: int, my: int) -> bool:
        """星星模式下左键点击处理：放置星星。"""
        wx, wy = self.screen_to_world(mx, my)
        if self.on_star_place:
            self.on_star_place(wx, wy)
        return True

    def _on_mouse_up(self, event) -> bool:
        # 结束平移
        if event.button in (2, 3) and self._panning:
            self._panning = False
            return True

        # 左键释放
        if event.button == 1:
            if self._drag_pending:
                # 拖拽待决 → 未超过阈值，视为纯点击
                self._drag_pending = False
                self._drag_moved = False
                self.dragging_node = None
                return True
            # 真正拖拽结束
            self.dragging_node = None
            self._drag_pending = False
            self._drag_moved = False
            return True

        return False

    def _on_mouse_motion(self, event) -> bool:
        mx, my = event.pos

        # 平移画布
        if self._panning:
            dx = mx - self._pan_start[0]
            dy = my - self._pan_start[1]
            self.offset_x = self._pan_offset_start[0] + dx
            self.offset_y = self._pan_offset_start[1] + dy
            return True

        # 拖拽移动节点（带阈值检测）
        if self._drag_pending and self.dragging_node is not None:
            dx = mx - self._drag_start_pos[0]
            dy = my - self._drag_start_pos[1]
            if not self._drag_moved:
                # 未超过阈值 → 检查是否超过
                if dx * dx + dy * dy >= DRAG_THRESHOLD * DRAG_THRESHOLD:
                    self._drag_moved = True
                    # 真正开始拖拽 → 保存撤销状态
                    if self.on_node_drag_start:
                        self.on_node_drag_start()
            if self._drag_moved:
                wx, wy = self.screen_to_world(mx, my)
                self.model.move_node(self.dragging_node, wx, wy)
            return True

        # 更新悬停
        if self._in_canvas(mx, my):
            self.hover_node = self.find_node_at_screen(mx, my)
        else:
            self.hover_node = None

        return False

    def _on_mouse_wheel(self, event) -> bool:
        mx, my = pygame.mouse.get_pos()
        if not self._in_canvas(mx, my):
            return False

        # 以鼠标位置为中心缩放
        old_scale = self.scale
        if event.y > 0:
            self.scale = min(MAX_SCALE, self.scale * (1 + ZOOM_STEP))
        elif event.y < 0:
            self.scale = max(MIN_SCALE, self.scale * (1 - ZOOM_STEP))

        # 调整偏移使鼠标位置不变
        ratio = self.scale / old_scale
        self.offset_x = mx - (mx - self.offset_x) * ratio
        self.offset_y = my - (my - self.offset_y) * ratio
        return True

    def cancel_line(self) -> None:
        """取消当前连线操作。"""
        self.line_start_nid = None
        self.is_drawing_line = False

    # ─── 绘制 ────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface) -> None:
        """绘制画布内容：边、连线预览、节点、星星、悬停提示。"""
        self._draw_edges(surface)
        self._draw_line_preview(surface)
        self._draw_nodes(surface)
        self._draw_star_points(surface)
        self._draw_hover_tip(surface)

    def _draw_edges(self, surface: pygame.Surface) -> None:
        """绘制所有边（双线道路风格）。"""
        for u, v in self.model.edges:
            pos_u = self.model.node_pos(u)
            pos_v = self.model.node_pos(v)
            if pos_u is None or pos_v is None:
                continue
            su = self.world_to_screen(*pos_u)
            sv = self.world_to_screen(*pos_v)
            # 底层宽线（道路边框）
            w = max(2, int(4 * self.scale))
            pygame.draw.line(surface, (120, 110, 90), su, sv, w + 2)
            # 上层窄线（道路填充）
            pygame.draw.line(surface, (180, 170, 150), su, sv, w)

    def _draw_line_preview(self, surface: pygame.Surface) -> None:
        """绘制连线虚线预览（wiring_mode 或右键连线时）。"""
        if not self.is_drawing_line or self.line_start_nid is None:
            return
        pos = self.model.node_pos(self.line_start_nid)
        if pos is None:
            self.cancel_line()
            return
        sx, sy = self.world_to_screen(*pos)
        mx, my = pygame.mouse.get_pos()
        # 连线模式用亮绿色虚线，普通模式用白色虚线
        line_color = (100, 255, 100) if self.wiring_mode else (255, 255, 255)
        dx, dy = mx - sx, my - sy
        length = math.hypot(dx, dy)
        if length < 1:
            return
        step = 8
        seg_count = max(1, int(length / step))
        for i in range(0, seg_count, 2):
            t1 = i / seg_count
            t2 = min((i + 1) / seg_count, 1.0)
            p1 = (int(sx + dx * t1), int(sy + dy * t1))
            p2 = (int(sx + dx * t2), int(sy + dy * t2))
            pygame.draw.line(surface, line_color, p1, p2, 2)

    def _draw_nodes(self, surface: pygame.Surface) -> None:
        """绘制所有节点。"""
        from .render_cache import get_cached_terrain
        for nid, nd in self.model.nodes.items():
            wx, wy = nd["x"], nd["y"]
            terrain = nd.get("terrain", "normal")
            color = TERRAIN_COLOR.get(terrain, FALLBACK_GRAY)
            is_hq = nid in (self.model.hq_red, self.model.hq_blue)
            radius = EDITOR_NODE_RADIUS + 4 if is_hq else EDITOR_NODE_RADIUS
            sr = self.scaled_radius(radius)
            sx, sy = self.world_to_screen(wx, wy)

            # 阴影
            shadow_rect = pygame.Rect(sx + 2 - sr, sy + 2 - sr, sr * 2, sr * 2)
            pygame.draw.rect(surface, (20, 20, 25), shadow_rect,
                             border_radius=TILE_ROUND_RADIUS + 2)
            # 节点主体（圆角方形）
            tile_rect = pygame.Rect(sx - sr, sy - sr, sr * 2, sr * 2)
            pygame.draw.rect(surface, color, tile_rect,
                             border_radius=TILE_ROUND_RADIUS)
            # 边框
            border_color = (60, 60, 70)
            pygame.draw.rect(surface, border_color, tile_rect, 2,
                             border_radius=TILE_ROUND_RADIUS)

            # 地形图标（缓存blit替代文字渲染）
            inner_half = sr - int(TILE_PADDING * self.scale)
            ter_size = max(4, int(inner_half * 1.4))
            ter_surf = get_cached_terrain(terrain, target_size=ter_size)
            surface.blit(ter_surf, (sx - ter_surf.get_width() // 2,
                                    sy - ter_surf.get_height() // 2))

            # 选中高亮
            if nid == self.selected_node:
                pygame.draw.rect(surface, (255, 255, 0),
                                 tile_rect.inflate(6, 6), 3,
                                 border_radius=TILE_ROUND_RADIUS + 3)
            # 连线起点高亮（wiring_mode用绿色，否则白色）
            if self.is_drawing_line and nid == self.line_start_nid:
                hl_color = (100, 255, 100) if self.wiring_mode else (255, 255, 255)
                pygame.draw.rect(surface, hl_color,
                                 tile_rect.inflate(10, 10), 3,
                                 border_radius=TILE_ROUND_RADIUS + 5)
            # HQ 标记
            if nid == self.model.hq_red:
                pygame.draw.rect(surface, (200, 30, 30),
                                 tile_rect.inflate(6, 6), 3,
                                 border_radius=TILE_ROUND_RADIUS + 3)
            elif nid == self.model.hq_blue:
                pygame.draw.rect(surface, (30, 60, 200),
                                 tile_rect.inflate(6, 6), 3,
                                 border_radius=TILE_ROUND_RADIUS + 3)

    def _draw_hover_tip(self, surface: pygame.Surface) -> None:
        """绘制悬停节点提示。"""
        if self.hover_node is None:
            return
        nd = self.model.get_node(self.hover_node)
        if nd is None:
            return
        terrain = nd.get("terrain", "normal")
        info = f"节点{self.hover_node} | {terrain}"
        if self.hover_node == self.model.hq_red:
            info += " | 红HQ"
        elif self.hover_node == self.model.hq_blue:
            info += " | 蓝HQ"
        sx, sy = self.world_to_screen(nd["x"], nd["y"])
        draw_tooltip(surface, info, (sx + 15, sy - 10), pad=(8, 4))

    def _draw_star_points(self, surface: pygame.Surface) -> None:
        """绘制所有星星点位。"""
        from .render_cache import get_cached_star
        for sp in self.model.star_points:
            wx, wy = sp["x"], sp["y"]
            sx, sy = self.world_to_screen(wx, wy)
            # 星星图标尺寸根据缩放调整
            star_size = max(8, int(18 * self.scale))
            star_surf = get_cached_star("gray", target_size=star_size)
            surface.blit(star_surf, (sx - star_surf.get_width() // 2,
                                     sy - star_surf.get_height() // 2))
            # 星星模式下显示区域ID
            if self.star_mode and "area_id" in sp:
                area_font = get_font(10, style="chinese")
                aid_text = area_font.render(str(sp["area_id"]), True, (255, 220, 50))
                surface.blit(aid_text, (sx + star_size // 2 + 2, sy - 6))