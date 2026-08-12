"""
相机控制系统 — 世界坐标与屏幕坐标解耦。

提供拖拽平移、滚轮缩放、平滑居中、视口裁剪等能力。
零侵入原则：仅被 ui/ 目录引用，game/ 层不依赖。
"""

import pygame

from .ui_const import (
    CAMERA_MIN_ZOOM, CAMERA_MAX_ZOOM, CAMERA_ZOOM_FACTOR,
    CAMERA_SMOOTH_SPEED, CAMERA_FIT_PADDING,
)


class Camera:
    """视口相机：统一管理缩放、平移、坐标转换。

    替代原有 MapTransform，新增用户交互控制（拖拽/缩放/居中）。
    所有渲染坐标转换均通过此相机完成，逻辑层坐标保持不变。

    Attributes:
        offset_x/offset_y: 屏幕偏移（像素）
        zoom: 缩放倍率（1.0 = 原始大小）
        dirty: 变换是否已变更（供缓存刷新判断）
    """

    def __init__(self, screen_width=1280, screen_height=800):
        # 视口状态
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.zoom = 1.0

        # 屏幕尺寸
        self.screen_width = screen_width
        self.screen_height = screen_height

        # 缩放限制
        self.min_zoom = CAMERA_MIN_ZOOM
        self.max_zoom = CAMERA_MAX_ZOOM

        # 拖拽状态
        self.is_dragging = False
        self._drag_button = 0
        self._last_mouse_pos = (0, 0)

        # 平滑移动目标
        self._target_x = 0.0
        self._target_y = 0.0
        self._is_animating = False
        self._anim_speed = CAMERA_SMOOTH_SPEED  # 平滑插值速度

        # 震动系统
        self.shake_intensity = 0.0
        self.shake_decay = 6.0  # 衰减速率（每秒）
        self._shake_offset = (0, 0)

        # 变更标记（供 bg_dirty 判断）
        self.dirty = True

        # UI 区域保护（排除信息栏/手牌区后的可用视口）
        self._view_x = 0
        self._view_y = 0
        self._view_w = screen_width
        self._view_h = screen_height

    # ═══════════════════════════════════════════════════════════
    #  坐标转换（兼容 MapTransform 接口）
    # ═══════════════════════════════════════════════════════════

    @property
    def scale(self):
        """兼容 MapTransform.scale 属性。"""
        return self.zoom

    def world_to_screen(self, wx, wy):
        """世界坐标 → 屏幕坐标（含震动偏移）。"""
        sx = wx * self.zoom + self.offset_x + self._shake_offset[0]
        sy = wy * self.zoom + self.offset_y + self._shake_offset[1]
        return sx, sy

    def screen_to_world(self, sx, sy):
        """屏幕坐标 → 世界坐标。"""
        if self.zoom == 0:
            return 0.0, 0.0
        wx = (sx - self.offset_x) / self.zoom
        wy = (sy - self.offset_y) / self.zoom
        return wx, wy

    def apply_to_size(self, value):
        """将世界尺寸转换为屏幕尺寸。"""
        return value * self.zoom

    def scaled_radius(self, world_radius):
        """将世界半径转换为屏幕半径，保证最小1像素。"""
        return max(1, int(world_radius * self.zoom))

    def scaled_click_radius(self, world_radius):
        """将屏幕点击半径反算为世界半径。"""
        if self.zoom == 0:
            return world_radius
        return world_radius / self.zoom

    # ═══════════════════════════════════════════════════════════
    #  事件处理
    # ═══════════════════════════════════════════════════════════

    def handle_event(self, event):
        """处理鼠标拖拽与滚轮缩放事件。

        Returns:
            bool: 是否消费了该事件（True = 事件已处理，不再传递）
        """
        if event.type == pygame.MOUSEBUTTONDOWN:
            # 中键(2)或右键(3)拖拽平移
            if event.button in (2, 3):
                self.is_dragging = True
                self._drag_button = event.button
                self._last_mouse_pos = event.pos
                self._is_animating = False  # 手动操作打断自动平滑
                return True

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == self._drag_button and self.is_dragging:
                self.is_dragging = False
                self._drag_button = 0
                return True

        elif event.type == pygame.MOUSEMOTION:
            if self.is_dragging:
                dx = event.pos[0] - self._last_mouse_pos[0]
                dy = event.pos[1] - self._last_mouse_pos[1]
                self.offset_x += dx
                self.offset_y += dy
                self._last_mouse_pos = event.pos
                self.dirty = True
                return True

        elif event.type == pygame.MOUSEWHEEL:
            self._handle_scroll(event.y, pygame.mouse.get_pos())
            return True

        return False

    def _handle_scroll(self, scroll_y, mouse_pos):
        """滚轮缩放：以鼠标位置为锚点。"""
        mouse_x, mouse_y = mouse_pos

        # 缩放前的世界坐标
        world_x_before, world_y_before = self.screen_to_world(mouse_x, mouse_y)

        # 调整缩放倍率
        zoom_factor = CAMERA_ZOOM_FACTOR if scroll_y > 0 else 1.0 / CAMERA_ZOOM_FACTOR
        new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * zoom_factor))

        if new_zoom != self.zoom:
            self.zoom = new_zoom
            # 重新调整 offset，保持鼠标指向的世界坐标位置不变
            self.offset_x = mouse_x - world_x_before * self.zoom
            self.offset_y = mouse_y - world_y_before * self.zoom
            self.dirty = True

    # ═══════════════════════════════════════════════════════════
    #  帧更新
    # ═══════════════════════════════════════════════════════════

    def add_shake(self, intensity):
        """触发屏幕震动。"""
        self.shake_intensity = max(self.shake_intensity, intensity)

    def update(self, dt):
        """每帧更新：平滑移动插值 + 震动衰减。"""
        # 平滑移动
        if self._is_animating:
            speed = self._anim_speed * dt
            self.offset_x += (self._target_x - self.offset_x) * speed
            self.offset_y += (self._target_y - self.offset_y) * speed

            # 接近目标点时停止动画
            if (abs(self._target_x - self.offset_x) < 0.5 and
                    abs(self._target_y - self.offset_y) < 0.5):
                self.offset_x = self._target_x
                self.offset_y = self._target_y
                self._is_animating = False

            self.dirty = True

        # 震动衰减
        if self.shake_intensity > 0.1:
            self.shake_intensity = max(0.0, self.shake_intensity - self.shake_decay * dt)
            import random
            ox = random.uniform(-self.shake_intensity, self.shake_intensity)
            oy = random.uniform(-self.shake_intensity, self.shake_intensity)
            self._shake_offset = (ox, oy)
            self.dirty = True
        elif self._shake_offset != (0, 0):
            self._shake_offset = (0, 0)
            self.dirty = True

    # ═══════════════════════════════════════════════════════════
    #  自适应与居中
    # ═══════════════════════════════════════════════════════════

    def fit_to_world(self, world_bounds, view_rect=None, padding_ratio=CAMERA_FIT_PADDING):
        """自适应缩放：使世界包围盒完整显示在视口内。

        Args:
            world_bounds: (min_x, min_y, max_x, max_y) 世界坐标包围盒
            view_rect: (x, y, w, h) 可用视口区域，None 则使用全屏
            padding_ratio: 边距比例（0.95 = 留5%边距）
        """
        min_x, min_y, max_x, max_y = world_bounds
        world_w = max(max_x - min_x, 1)
        world_h = max(max_y - min_y, 1)

        if view_rect is not None:
            self._view_x, self._view_y = view_rect[0], view_rect[1]
            self._view_w, self._view_h = view_rect[2], view_rect[3]
        else:
            self._view_x = 0
            self._view_y = 0
            self._view_w = self.screen_width
            self._view_h = self.screen_height

        # 等比缩放 + 边距
        scale_x = self._view_w / world_w if world_w > 0 else 1.0
        scale_y = self._view_h / world_h if world_h > 0 else 1.0
        self.zoom = min(scale_x, scale_y) * padding_ratio
        self.zoom = max(self.min_zoom, min(self.zoom, self.max_zoom))

        # 居中偏移
        scaled_w = world_w * self.zoom
        scaled_h = world_h * self.zoom
        self.offset_x = (self._view_w - scaled_w) / 2 + self._view_x - min_x * self.zoom
        self.offset_y = (self._view_h - scaled_h) / 2 + self._view_y - min_y * self.zoom

        self.dirty = True

    def center_on_world_pos(self, world_x, world_y, smooth=True):
        """一键居中到指定的世界坐标（如基地）。

        Args:
            world_x, world_y: 世界坐标
            smooth: True 则平滑移动，False 则立即跳转
        """
        target_offset_x = (self.screen_width / 2) - (world_x * self.zoom)
        target_offset_y = (self.screen_height / 2) - (world_y * self.zoom)

        if smooth:
            self._target_x = target_offset_x
            self._target_y = target_offset_y
            self._is_animating = True
        else:
            self.offset_x = target_offset_x
            self.offset_y = target_offset_y
            self.dirty = True

    # ═══════════════════════════════════════════════════════════
    #  视口裁剪
    # ═══════════════════════════════════════════════════════════

    def on_resize(self, screen_width, screen_height):
        """窗口大小改变时更新屏幕尺寸。"""
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.dirty = True