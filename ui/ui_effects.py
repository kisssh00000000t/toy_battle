"""
UI 视觉特效模块：高质感"玩具桌面"渲染增强。

组件：
    VignetteEffect: 暗角效果（同心圆角矩形叠加，15% Alpha）
    draw_toy_plastic_road: 塑料轨道连线（圆头端点+主线+白色高光弧）
"""

import math
from typing import Optional

import pygame

# ─── 暗角效果 ────────────────────────────────────────────────

class VignetteEffect:
    """暗角效果：在屏幕边缘叠加半透明暗角，增强视觉聚焦。

    特性：
    - 同心圆角矩形叠加，从外到内 Alpha 递减
    - 预渲染到缓存 Surface，避免每帧重绘
    - 支持动态调整强度和边框宽度

    使用方式：
        vignette = VignetteEffect(screen.get_size())
        vignette.render(screen)  # 每帧调用
    """

    # 默认参数
    DEFAULT_LAYERS = 6          # 暗角层数
    DEFAULT_MAX_ALPHA = 38      # 最外层 Alpha（约 15%）
    DEFAULT_BORDER_RATIO = 0.12 # 暗角宽度占屏幕短边比例
    DEFAULT_RADIUS = 18         # 圆角半径

    def __init__(self, screen_size: tuple[int, int],
                 layers: int = DEFAULT_LAYERS,
                 max_alpha: int = DEFAULT_MAX_ALPHA,
                 border_ratio: float = DEFAULT_BORDER_RATIO,
                 radius: int = DEFAULT_RADIUS):
        """初始化暗角效果。

        Args:
            screen_size: 屏幕尺寸 (width, height)
            layers: 暗角层数
            max_alpha: 最外层 Alpha 值 (0-255)
            border_ratio: 暗角宽度占屏幕短边比例
            radius: 圆角半径
        """
        self._size = screen_size
        self._layers = layers
        self._max_alpha = max_alpha
        self._border_ratio = border_ratio
        self._radius = radius
        self._cache: Optional[pygame.Surface] = None
        self._dirty = True

    def set_size(self, size: tuple[int, int]) -> None:
        """更新屏幕尺寸，标记缓存失效。"""
        if size != self._size:
            self._size = size
            self._dirty = True

    def set_intensity(self, max_alpha: int) -> None:
        """调整暗角强度。"""
        if max_alpha != self._max_alpha:
            self._max_alpha = max_alpha
            self._dirty = True

    def render(self, surface: pygame.Surface) -> None:
        """将暗角效果叠加到目标 Surface 上。

        Args:
            surface: 目标渲染表面
        """
        if self._dirty or self._cache is None:
            self._build_cache()

        if self._cache is not None:
            surface.blit(self._cache, (0, 0))

    def _build_cache(self) -> None:
        """预渲染暗角到缓存 Surface。"""
        w, h = self._size
        self._cache = pygame.Surface((w, h), pygame.SRCALPHA)
        self._cache.fill((0, 0, 0, 0))

        short_side = min(w, h)
        border = int(short_side * self._border_ratio)
        radius = self._radius

        for i in range(self._layers):
            # 从外到内：Alpha 递减，矩形递增
            t = i / max(self._layers - 1, 1)  # 0.0(外) ~ 1.0(内)
            alpha = int(self._max_alpha * (1.0 - t))
            inset = int(border * t)

            rect = pygame.Rect(inset, inset, w - 2 * inset, h - 2 * inset)
            if rect.width <= 0 or rect.height <= 0:
                continue

            # 绘制圆角矩形边框（填充边框区域）
            self._draw_rounded_rect_border(self._cache, rect, radius, alpha)

        self._dirty = False

    @staticmethod
    def _draw_rounded_rect_border(surface: pygame.Surface, rect: pygame.Rect,
                                   radius: int, alpha: int) -> None:
        """在 Surface 上绘制圆角矩形边框区域（仅边框，内部透明）。

        通过绘制完整圆角矩形再抠掉内部实现。
        """
        color = (0, 0, 0, alpha)
        # 使用 pygame.draw.rect 的圆角功能
        # 绘制完整填充圆角矩形
        temp = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(temp, color, (0, 0, rect.width, rect.height),
                         border_radius=radius)

        # 抠掉内部（缩小一定像素的矩形）
        shrink = max(2, int(min(rect.width, rect.height) * 0.06))
        inner = pygame.Rect(shrink, shrink,
                             rect.width - 2 * shrink, rect.height - 2 * shrink)
        if inner.width > 0 and inner.height > 0:
            pygame.draw.rect(temp, (0, 0, 0, 0), inner,
                             border_radius=max(0, radius - shrink))

        surface.blit(temp, rect.topleft)


# ─── 塑料轨道连线 ────────────────────────────────────────────

def draw_toy_plastic_road(surface: pygame.Surface,
                           start: tuple[int, int],
                           end: tuple[int, int],
                           color: tuple[int, int, int],
                           width: int = 8,
                           highlight_color: Optional[tuple[int, int, int]] = None) -> None:
    """绘制高质感塑料轨道连线。

    特性：
    - 圆头端点（圆形端帽）
    - 主线（指定颜色和宽度）
    - 白色高光反射弧（偏移主线中心，半透明白色）

    Args:
        surface: 目标渲染表面
        start: 起点坐标 (x, y)
        end: 终点坐标 (x, y)
        color: 轨道主色 (R, G, B)
        width: 轨道宽度（像素）
        highlight_color: 高光颜色，默认 (255, 255, 255)
    """
    if highlight_color is None:
        highlight_color = (255, 255, 255)

    sx, sy = start
    ex, ey = end

    # ── 主线（圆头端点）──
    # pygame.draw.line 不支持圆头，用 aaline + 圆形端帽模拟
    half_w = width // 2

    # 绘制主线
    pygame.draw.line(surface, color, (sx, sy), (ex, ey), width)

    # 圆头端帽
    pygame.draw.circle(surface, color, (sx, sy), half_w)
    pygame.draw.circle(surface, color, (ex, ey), half_w)

    # ── 白色高光弧 ──
    dx = ex - sx
    dy = ey - sy
    length = math.hypot(dx, dy)
    if length < 1:
        return

    # 法线方向（垂直于线段）
    nx = -dy / length
    ny = dx / length

    # 高光偏移：主线宽度的 1/4
    offset = width * 0.25
    hl_alpha = 80  # 约 31% 透明度

    # 高光起点和终点（偏移后的线段）
    hl_sx = sx + nx * offset
    hl_sy = sy + ny * offset
    hl_ex = ex + nx * offset
    hl_ey = ey + ny * offset

    # 高光线宽为主线的 1/3
    hl_width = max(2, width // 3)

    # 在临时 Surface 上绘制高光（带 Alpha）
    # 计算包围盒
    min_x = int(min(hl_sx, hl_ex)) - hl_width - 2
    min_y = int(min(hl_sy, hl_ey)) - hl_width - 2
    max_x = int(max(hl_sx, hl_ex)) + hl_width + 2
    max_y = int(max(hl_sy, hl_ey)) + hl_width + 2

    temp_w = max_x - min_x
    temp_h = max_y - min_y
    if temp_w <= 0 or temp_h <= 0:
        return

    temp = pygame.Surface((temp_w, temp_h), pygame.SRCALPHA)
    local_start = (int(hl_sx - min_x), int(hl_sy - min_y))
    local_end = (int(hl_ex - min_x), int(hl_ey - min_y))

    hl_color_with_alpha = (*highlight_color, hl_alpha)
    pygame.draw.line(temp, hl_color_with_alpha, local_start, local_end, hl_width)

    # 高光端帽
    hl_half = hl_width // 2
    pygame.draw.circle(temp, hl_color_with_alpha, local_start, hl_half)
    pygame.draw.circle(temp, hl_color_with_alpha, local_end, hl_half)

    surface.blit(temp, (min_x, min_y))