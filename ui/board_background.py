"""
棋盘背景预渲染：木纹桌面 + 区域淡色填充。
替代纯色 fill，在 _rebuild_bg_cache 中调用。
"""
import math
import random
import pygame
from .ui_const import AREA_BOUNDS_COLORS
from .widgets import draw_rounded_rect


def build_board_background(width, height):
    """预渲染桌面背景（不含棋盘元素，仅木纹底色）。

    Returns:
        pygame.Surface: 背景 Surface
    """
    surf = pygame.Surface((width, height))
    # 垂直渐变木纹
    for y in range(height):
        t = y / max(height, 1)
        r = int(248 - 18 * t)
        g = int(240 - 14 * t)
        b = int(222 - 10 * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (width, y))

    # 木纹细线（固定种子保证一致）
    rng = random.Random(42)
    for _ in range(80):
        y = rng.randint(0, height - 1)
        alpha = rng.randint(6, 16)
        length = rng.randint(width // 4, width)
        x_start = rng.randint(0, width - length)
        line_surf = pygame.Surface((length, 1), pygame.SRCALPHA)
        line_surf.fill((160, 140, 110, alpha))
        surf.blit(line_surf, (x_start, y))

    # 桌面边缘暗角（四角渐变）
    corner = pygame.Surface((width, height), pygame.SRCALPHA)
    for i in range(40):
        a = int(30 * (1 - i / 40))
        pygame.draw.rect(corner, (120, 100, 70, a),
                         (i, i, width - 2 * i, height - 2 * i), 1)
    surf.blit(corner, (0, 0))

    return surf


def draw_area_tints(surface, board, camera):
    """在棋盘上绘制区域淡色填充（提高可见度）。

    Args:
        surface: 目标 Surface
        board: Board 对象
        camera: Camera 对象
    """
    area_nodes = {}
    for nid, nd in board.nodes.items():
        area_nodes.setdefault(nd.area_id, []).append(nd)

    for aid, nodes in area_nodes.items():
        if len(nodes) < 2:
            continue
        xs = [camera.world_to_screen(n.x, n.y)[0] for n in nodes]
        ys = [camera.world_to_screen(n.x, n.y)[1] for n in nodes]
        pad = int(28 * camera.zoom)
        rect = pygame.Rect(
            int(min(xs) - pad), int(min(ys) - pad),
            int(max(xs) - min(xs) + pad * 2),
            int(max(ys) - min(ys) + pad * 2),
        )
        if rect.width < 10 or rect.height < 10:
            continue
        color = AREA_BOUNDS_COLORS[aid % len(AREA_BOUNDS_COLORS)]
        tint = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        draw_rounded_rect(tint, (*color, 38), tint.get_rect(), radius=16)
        surface.blit(tint, rect.topleft)