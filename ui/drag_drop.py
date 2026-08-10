"""
拖拽管理器。

统一处理拖拽交互：按住 → 生成半透明拖影 → 跟随鼠标 → 松开释放。
支持自适应旋转（长条物体旋转幅度小）和弹性缩放动效。
"""

import pygame
from .tween_manager import TWEEN
from .easing import EASE_BACK_OUT


class DragDropManager:
    """拖拽管理器，处理拖起/跟随/释放全流程。"""

    def __init__(self):
        self.dragging = False
        self.drag_object = None          # 拖拽的数据对象（Troop / terrain_key）
        self.drag_surface = None         # 跟随鼠标的半透明 Surface
        self.drag_source_rect = None     # 拖拽起始区域（用于计算偏移）
        self.current_target = None       # 当前悬停的目标（节点/None）
        self.on_drop_callback = None     # 释放回调: callback(drag_object, target)
        self.find_target_func = None     # 目标检测函数: func(mx, my) -> target

        # 动效状态
        self.hover_scale = 1.0
        self.hover_rotation = 0.0        # 度
        self._max_rotation = 8.0         # 最大旋转角度

    def start_drag(self, obj, source_rect, drag_image):
        """开始拖拽。

        Args:
            obj: 拖拽数据（Troop 实例 / 地形 key 字符串）
            source_rect: 拖拽起始区域 pygame.Rect
            drag_image: 拖影 Surface（会被复制并设为半透明）
        """
        self.dragging = True
        self.drag_object = obj
        self.drag_source_rect = pygame.Rect(source_rect)
        # 创建半透明拖影
        self.drag_surface = drag_image.copy()
        self.drag_surface.set_alpha(200)
        # 弹入动效
        self.hover_scale = 0.8
        TWEEN.kill_tween(self, "hover_scale")
        TWEEN.create_tween(self, "hover_scale", 1.12, 0.15, ease_type=EASE_BACK_OUT)
        # 自适应旋转：根据宽高比限制旋转幅度
        w, h = drag_image.get_size()
        ratio = max(w, h) / (min(w, h) + 0.01)
        if ratio > 2.0:
            self._max_rotation = 3.0
        elif ratio > 1.5:
            self._max_rotation = 5.0
        else:
            self._max_rotation = 8.0
        self.hover_rotation = 0.0

    def stop_drag(self):
        """停止拖拽，清理状态。"""
        self.dragging = False
        self.drag_object = None
        self.drag_surface = None
        self.drag_source_rect = None
        self.current_target = None
        self.hover_scale = 1.0
        self.hover_rotation = 0.0

    def handle_event(self, event):
        """处理事件，在拖拽状态下拦截鼠标移动和释放。"""
        if not self.dragging:
            return False  # 未拦截

        if event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            # 更新悬停目标
            if self.find_target_func:
                self.current_target = self.find_target_func(mx, my)
            else:
                self.current_target = None
            # 根据鼠标水平偏移计算旋转
            if self.drag_source_rect:
                dx = mx - self.drag_source_rect.centerx
                self.hover_rotation = max(-self._max_rotation,
                                          min(self._max_rotation, dx * 0.04))
            return True  # 拦截事件

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            # 释放：如果有目标则回调
            if self.on_drop_callback and self.current_target is not None:
                self.on_drop_callback(self.drag_object, self.current_target)
            self.stop_drag()
            return True  # 拦截事件

        return False  # 其他事件不拦截

    def draw(self, surface):
        """绘制拖影（缩放+旋转+半透明）。"""
        if not self.dragging or not self.drag_surface:
            return
        mx, my = pygame.mouse.get_pos()
        # 缩放 + 旋转
        scaled = pygame.transform.rotozoom(self.drag_surface,
                                           -self.hover_rotation,
                                           self.hover_scale)
        rect = scaled.get_rect(center=(mx, my))
        surface.blit(scaled, rect)

    def draw_target_highlight(self, surface, target_pos_func=None, valid_check_func=None,
                                  highlight_radius=30, highlight_width=4):
        """在拖拽时高亮当前悬停的目标节点。

        Args:
            surface: 绘制目标
            target_pos_func: 可选，函数(target) -> (x, y)，获取目标位置
            valid_check_func: 可选，函数(target) -> bool，检查目标是否有效
            highlight_radius: 高亮圆环半径
            highlight_width: 高亮圆环线宽
        """
        if not self.dragging or self.current_target is None:
            return
        target = self.current_target
        # 检查有效性
        if valid_check_func and not valid_check_func(target):
            return
        # 获取位置
        if target_pos_func:
            pos = target_pos_func(target)
            if pos is None:
                return
            x, y = int(pos[0]), int(pos[1])
        elif hasattr(target, 'x') and hasattr(target, 'y'):
            x, y = int(target.x), int(target.y)
        else:
            return
        # 绘制高亮圆环
        from .widgets import TOY_COLORS
        pygame.draw.circle(surface, TOY_COLORS["primary_yellow"], (x, y),
                           highlight_radius, highlight_width)