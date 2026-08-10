"""
UI 通用绘制工具函数。

提供 Alpha 安全的圆角面板绘制、桌面网格纹理生成等基础能力。
所有 UI 组件的底层绘制应通过此模块完成，禁止在组件中直接调用 pygame.draw。
"""

import pygame
from .ui_const import (
    BG_CREAM, GRID_TILE_SIZE, GRID_LINE_COLOR, GRID_LINE_WIDTH,
    TOOLTIP_BG,
)


def make_grid_tile(size=GRID_TILE_SIZE, line_color=GRID_LINE_COLOR,
                   line_width=GRID_LINE_WIDTH):
    """生成桌面网格纹理平铺单元。

    生成一张小 Surface（如 32×32px），上面绘制 alpha 值极低的网格线条。
    在主 Surface 上通过双重循环平铺（Tile Blit），实现桌面纹理效果。
    内存占用极低，且适配任意屏幕分辨率。

    Args:
        size: 平铺单元尺寸（像素），默认 GRID_TILE_SIZE
        line_color: 网格线颜色 (R,G,B,A)，默认 GRID_LINE_COLOR
        line_width: 网格线宽度，默认 GRID_LINE_WIDTH

    Returns:
        pygame.Surface: 可平铺的网格纹理单元
    """
    tile = pygame.Surface((size, size), pygame.SRCALPHA)
    # 只绘制右边缘和底边缘线条，平铺后自然形成完整网格
    # 底边
    pygame.draw.line(tile, line_color, (0, size - 1), (size - 1, size - 1), line_width)
    # 右边
    pygame.draw.line(tile, line_color, (size - 1, 0), (size - 1, size - 1), line_width)
    return tile


def tile_blit_grid(surface, tile_surf, area_rect=None):
    """将网格纹理平铺到目标 Surface 的指定区域。

    Args:
        surface: 目标 Surface
        tile_surf: 网格纹理单元（由 make_grid_tile 生成）
        area_rect: 平铺区域，None 则填充整个 surface
    """
    if area_rect is None:
        area_rect = surface.get_rect()
    tw, th = tile_surf.get_size()
    x0, y0 = area_rect.topleft
    x_end = area_rect.right
    y_end = area_rect.bottom
    for y in range(y0, y_end, th):
        for x in range(x0, x_end, tw):
            surface.blit(tile_surf, (x, y))


def draw_alpha_rect(surface, color_rgba, rect, radius=0):
    """在目标 Surface 上绘制带 Alpha 的圆角矩形（仅填充，无边框）。

    简化版 draw_rounded_panel，用于快速绘制半透明色块。

    Args:
        surface: 目标 Surface
        color_rgba: 颜色 (R,G,B,A)
        rect: 矩形区域
        radius: 圆角半径，0 则直角
    """
    rect = pygame.Rect(rect)
    shape_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    if radius > 0:
        pygame.draw.rect(shape_surf, color_rgba, shape_surf.get_rect(),
                         border_radius=radius)
    else:
        shape_surf.fill(color_rgba)
    surface.blit(shape_surf, rect.topleft)


def draw_tooltip(surface, text, pos, font=None, pad=(10, 6), radius=6):
    """在指定位置绘制深色背景 Tooltip。

    Args:
        surface: 目标 Surface
        text: 提示文本
        pos: 文本基准位置 (x, y)，即 bg_rect 的 topleft
        font: 字体对象，None 则使用默认 16 号中文字体
        pad: 内边距 (水平, 垂直)，默认 (10, 6)
        radius: 圆角半径，默认 6
    """
    if font is None:
        from .widgets import get_font
        font = get_font(16, style="chinese")
    txt_surf = font.render(text, True, (255, 255, 255))
    bg_rect = txt_surf.get_rect(topleft=pos)
    bg_rect.inflate_ip(pad[0], pad[1])
    pygame.draw.rect(surface, TOOLTIP_BG, bg_rect, border_radius=radius)
    surface.blit(txt_surf, (pos[0] + pad[0] // 2, pos[1] + pad[1] // 2))


def point_in_polygon(px: float, py: float, polygon: list) -> bool:
    """射线法判断点是否在多边形内部。

    从点 (px, py) 向右发射水平射线，统计与多边形边的交点数：
    奇数交点 → 点在内部，偶数交点 → 点在外部。

    Args:
        px: 待检测点 X 坐标
        py: 待检测点 Y 坐标
        polygon: 多边形顶点列表 [(x1,y1), (x2,y2), ...]，至少3个顶点

    Returns:
        True 表示点在多边形内部（含边界），False 表示在外部
    """
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        # 判断射线是否穿过边 (xi,yi)-(xj,yj)
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside