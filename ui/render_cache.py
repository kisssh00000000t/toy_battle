"""
预渲染图标缓存管理器（PNG优先 + 几何回退）。

启动时一次性预渲染所有兵种、地形、星星图标到独立 Surface，
运行时直接 blit 缓存，消除每帧大量三角函数/多边形计算开销。

双轨加载策略：
1. PNG优先：若 assets/ 下有对应 PNG 素材，直接加载缩放缓存
2. 几何回退：PNG 不存在时，使用 widgets.draw_* 函数实时绘制

星星 API：
- get_cached_star(state, target_size)  state="gray"/"red"/"blue"

缓存持久化：
- use_persist_cache=True: 首次绘制保存 PNG 到 assets/cache/，后续直接加载
"""

import logging
from pathlib import Path
from typing import Optional

import pygame

from .ui_const import FALLBACK_GRAY
from game.constants import TROOP_DATA, TERRAIN_DATA, PLAYER_COLORS

logger = logging.getLogger(__name__)

# 缓存目录（持久预渲染图存放）
CACHE_DIR = Path(__file__).parent.parent / "assets" / "cache"

# 全局内存缓存容器
ICON_CACHE: dict = {
    "troop": {},       # {troop_key: {color_key: Surface}}
    "terrain": {},     # {ter_key: Surface}
    "star": {},        # {(state, size): Surface}  state="gray"/"red"/"blue"
}

# 标准预渲染尺寸
TROOP_ICON_SIZE = 48
TERRAIN_ICON_SIZE = 64   # 地形基准尺寸提升到 64（匹配素材规范）
STAR_SIZES = [10, 14, 18, 22]  # 预渲染尺寸列表（防遮挡缩小）

# 星星状态定义
STAR_STATES = ["gray", "red", "blue"]

# 星星状态对应颜色（几何回退时使用）
STAR_STATE_COLORS = {
    "gray": {"fill": FALLBACK_GRAY, "stroke": (120, 120, 120), "filled": False},
    "red": {"fill": (255, 210, 0), "stroke": (200, 150, 0), "filled": True},
    "blue": {"fill": (100, 160, 255), "stroke": (60, 100, 200), "filled": True},
}

# 兵种归属方颜色键
_OWNER_COLOR_KEYS = list(PLAYER_COLORS.keys()) + ["neutral"]


def _ensure_cache_dir():
    """确保缓存目录存在。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(category: str, name: str, size: int) -> Path:
    """获取缓存文件路径。"""
    return CACHE_DIR / f"{category}_{name}_{size}.png"


def _load_persist(path: Path) -> Optional[pygame.Surface]:
    """从本地缓存加载 PNG，不存在返回 None。"""
    if not path.exists():
        return None
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except Exception:
        return None


def _save_persist(surf: pygame.Surface, path: Path):
    """保存预渲染图到本地缓存。"""
    try:
        _ensure_cache_dir()
        pygame.image.save(surf, str(path))
    except Exception as e:
        logger.warning(f"保存缓存失败 {path}: {e}")


def pre_render_all_icons(use_persist_cache: bool = True):
    """程序启动一次性预渲染所有图标，存入 ICON_CACHE。

    加载策略：
    1. 尝试从 asset_loader 加载 PNG 素材（支持双套样式）
    2. PNG 不存在时回退到几何绘制
    3. 支持持久 PNG 缓存加速后续启动

    Args:
        use_persist_cache: True=优先从 PNG 缓存加载，False=每次重绘
    """
    # 延迟导入避免循环依赖
    from .widgets import draw_star_shape, draw_troop_icon, draw_terrain_icon
    from .asset_loader import (
        init_all_assets, get_terrain_img, get_troop_img, get_star_img,
        has_terrain_imgs, has_troop_imgs, has_star_imgs,
    )

    # 初始化素材加载器（含双套兵种图标预加载）
    init_all_assets()

    # 检查 PNG 素材可用性
    use_terrain_png = has_terrain_imgs()
    use_troop_png = has_troop_imgs()
    use_star_png = has_star_imgs()
    logger.info(f"素材状态: 地形PNG={use_terrain_png}, 士兵PNG={use_troop_png}, 星星PNG={use_star_png}")

    # 1. 预渲染星星（新API: gray/red/blue 三种状态 × 多种尺寸）
    for state in STAR_STATES:
        png_surf = get_star_img(state) if use_star_png else None
        for sz in STAR_SIZES:
            cache_key = (state, sz)
            cp = _cache_path("star", state, sz)
            surf = _load_persist(cp) if use_persist_cache else None
            if surf is None:
                if png_surf is not None:
                    # 从 PNG 素材缩放
                    surf = pygame.transform.smoothscale(png_surf, (sz * 2 + 4, sz * 2 + 4))
                else:
                    # 几何回退
                    colors = STAR_STATE_COLORS[state]
                    surf = pygame.Surface((sz * 2 + 4, sz * 2 + 4), pygame.SRCALPHA)
                    draw_star_shape(surf, sz + 2, sz + 2, sz,
                                    colors["fill"], colors["stroke"], 2,
                                    filled=colors["filled"])
                if use_persist_cache:
                    _save_persist(surf, cp)
            ICON_CACHE["star"][cache_key] = surf

    # 2. 预渲染全部兵种（各归属方颜色）
    _pre_render_troops(use_persist_cache=use_persist_cache)

    # 3. 预渲染全部地形图标
    for ter_key in TERRAIN_DATA.keys():
        png_surf = get_terrain_img(ter_key) if use_terrain_png else None
        cp = _cache_path("terrain", ter_key, TERRAIN_ICON_SIZE)
        surf = _load_persist(cp) if use_persist_cache else None
        if surf is None:
            surf = pygame.Surface((TERRAIN_ICON_SIZE, TERRAIN_ICON_SIZE), pygame.SRCALPHA)
            if png_surf is not None:
                # PNG 素材直接缩放
                scaled = pygame.transform.smoothscale(
                    png_surf, (TERRAIN_ICON_SIZE, TERRAIN_ICON_SIZE))
                surf.blit(scaled, (0, 0))
            else:
                # 几何回退
                fill_c = TERRAIN_DATA[ter_key].get("color", FALLBACK_GRAY)
                draw_terrain_icon(surf, TERRAIN_ICON_SIZE // 2, TERRAIN_ICON_SIZE // 2,
                                  TERRAIN_ICON_SIZE, ter_key, fill_c)
            if use_persist_cache:
                _save_persist(surf, cp)
        ICON_CACHE["terrain"][ter_key] = surf

    logger.info(f"图标预渲染完成: 兵种{len(ICON_CACHE['troop'])}种×{len(_OWNER_COLOR_KEYS)}色, "
                f"地形{len(ICON_CACHE['terrain'])}种, "
                f"星星{len(STAR_SIZES)}×{len(STAR_STATES)}状态")


# ─── 对外获取接口 ──────────────────────────────────────────

def get_cached_troop(troop_key, owner: str, target_size: int = 0,
                      target_scale: float = 1.0) -> pygame.Surface:
    """获取缓存兵种图标，自动缩放。

    Args:
        troop_key: 兵种key
        owner: 归属方 "red"/"blue"/"neutral"
        target_size: 目标尺寸（像素），优先于 target_scale
        target_scale: 缩放比例（当 target_size=0 时使用）

    Returns:
        缩放后的 Surface
    """
    color_key = owner if owner in ICON_CACHE["troop"].get(troop_key, {}) else "neutral"
    base_surf = ICON_CACHE["troop"].get(troop_key, {}).get(color_key)
    if base_surf is None:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    if target_size > 0:
        scale = target_size / TROOP_ICON_SIZE
    else:
        scale = target_scale
    if abs(scale - 1.0) < 0.01:
        return base_surf
    w, h = base_surf.get_size()
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    return pygame.transform.smoothscale(base_surf, (new_w, new_h))


def get_cached_terrain(ter_key: str, target_size: int = 0,
                        target_scale: float = 1.0) -> pygame.Surface:
    """获取缓存地形图标，自动缩放。"""
    base_surf = ICON_CACHE["terrain"].get(ter_key)
    if base_surf is None:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    if target_size > 0:
        scale = target_size / TERRAIN_ICON_SIZE
    else:
        scale = target_scale
    if abs(scale - 1.0) < 0.01:
        return base_surf
    w, h = base_surf.get_size()
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    return pygame.transform.smoothscale(base_surf, (new_w, new_h))


def get_cached_star(state: str, target_size: int) -> pygame.Surface:
    """获取缓存星星图标。

    Args:
        state: 星星状态 "gray"(未占领) / "red"(红方占领) / "blue"(蓝方占领)
        target_size: 目标外径尺寸

    Returns:
        缩放后的 Surface
    """
    # 新API: state + target_size
    best_sz = min(STAR_SIZES, key=lambda s: abs(s - target_size))
    base_surf = ICON_CACHE.get("star", {}).get((state, best_sz))
    if base_surf is None:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    if best_sz != target_size:
        scale = target_size / best_sz
        w, h = base_surf.get_size()
        new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
        return pygame.transform.smoothscale(base_surf, (new_w, new_h))
    return base_surf


# ═══════════════════════════════════════════════════════════
#  兵种样式切换支持
# ═══════════════════════════════════════════════════════════

# 当前已渲染的样式编号，用于判断是否需要刷新
_current_troop_style = None


def _pre_render_troops(use_persist_cache: bool = True):
    """预渲染全部兵种图标（各归属方颜色）。

    从 asset_loader 获取当前样式的 PNG 素材，生成阵营着色缓存。
    样式切换时调用此函数刷新兵种缓存。
    """
    global _current_troop_style
    from .widgets import draw_troop_icon
    from .asset_loader import get_troop_img, has_troop_imgs
    from .style_cache import get_current_icon_style

    current_style = get_current_icon_style()
    _current_troop_style = current_style
    use_troop_png = has_troop_imgs()

    for troop_key in TROOP_DATA.keys():
        ICON_CACHE["troop"][troop_key] = {}
        png_surf = get_troop_img(troop_key) if use_troop_png else None
        for c_key in _OWNER_COLOR_KEYS:
            color = PLAYER_COLORS.get(c_key, (160, 160, 160))
            cp = _cache_path("troop", f"{troop_key}_{c_key}", TROOP_ICON_SIZE)
            # 样式切换时跳过持久缓存（因为样式变了，缓存可能不匹配）
            surf = _load_persist(cp) if (use_persist_cache and _current_troop_style == 1) else None
            if surf is None:
                surf = pygame.Surface((TROOP_ICON_SIZE, TROOP_ICON_SIZE), pygame.SRCALPHA)
                if png_surf is not None:
                    # PNG 素材 + 底部阵营色条（不覆盖全图，避免彩虹圈变脏）
                    scaled = pygame.transform.smoothscale(
                        png_surf, (TROOP_ICON_SIZE, TROOP_ICON_SIZE))
                    surf.blit(scaled, (0, 0))
                    # 底部阵营色条
                    bar_h = max(3, TROOP_ICON_SIZE // 10)
                    bar = pygame.Surface((TROOP_ICON_SIZE, bar_h), pygame.SRCALPHA)
                    bar.fill((*color, 210))
                    surf.blit(bar, (0, TROOP_ICON_SIZE - bar_h))
                    # 底部高光线
                    hl = pygame.Surface((TROOP_ICON_SIZE, 1), pygame.SRCALPHA)
                    hl.fill((255, 255, 255, 120))
                    surf.blit(hl, (0, TROOP_ICON_SIZE - bar_h - 1))
                else:
                    # 几何回退（传入 style_id 以支持扩展兵种文字占位符）
                    draw_troop_icon(surf, TROOP_ICON_SIZE // 2, TROOP_ICON_SIZE // 2,
                                    TROOP_ICON_SIZE, troop_key, color, style_id=current_style)
                if use_persist_cache:
                    _save_persist(surf, cp)
            ICON_CACHE["troop"][troop_key][c_key] = surf

    logger.info(f"兵种图标预渲染完成: 样式{current_style}, {len(ICON_CACHE['troop'])}种×{len(_OWNER_COLOR_KEYS)}色")


def refresh_troop_cache():
    """样式切换后刷新兵种图标缓存。

    清除现有兵种缓存并重新预渲染，用于运行时切换图标样式。
    """
    from .style_cache import get_current_icon_style
    new_style = get_current_icon_style()
    if new_style == _current_troop_style:
        logger.debug(f"样式未变化(样式{new_style})，跳过刷新")
        return
    logger.info(f"刷新兵种图标缓存: 样式{_current_troop_style} → 样式{new_style}")
    # 清除现有兵种缓存
    ICON_CACHE["troop"].clear()
    # 重新预渲染
    _pre_render_troops(use_persist_cache=False)