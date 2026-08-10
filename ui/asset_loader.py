"""
素材加载器。

统一管理 PNG 素材的加载和缓存，支持优雅回退：
- 优先从本地 PNG 文件加载美术素材
- PNG 不存在时返回 None，由 render_cache 回退到几何绘制
- 支持多套兵种图标样式切换（由 styles_registry 驱动）

素材目录结构：
  assets/
  ├── ui_terrain_img/    # 地形贴图 (64×64 PNG)
  ├── troop_icon_img/    # 士兵图标 样式1 (48×48 PNG)
  ├── star_icon_img/     # 星星图标 (32×32 PNG)
  ├── cache/             # 预渲染缓存（程序自动生成）
  ├── fonts/
  ├── ui_btn/
  ├── ui_panel/
  └── bg/
  cut/
  ├── new1/              # 士兵图标 样式2 (960×960 PNG)
  ├── new2/              # 士兵图标 样式3 旧目录 (卡通风格 PNG, 仅 troop 1~7)
  └── new3/              # 士兵图标 样式3 (卡通风格 PNG, 含 troop 8~17 扩展兵种)
"""

import logging
from pathlib import Path
from typing import Dict, Optional

import pygame

logger = logging.getLogger(__name__)

# 素材根目录
ASSET_ROOT = Path(__file__).parent.parent / "assets"

# 全局素材缓存 {folder_name: {key: Surface}}
_assets: Dict[str, Dict[str, pygame.Surface]] = {}

# 多套兵种图标缓存 {style_id: {filename_stem: Surface}}
# 由 styles_registry 驱动，支持任意数量样式
_troop_style_cache: Dict[int, Dict[str, pygame.Surface]] = {}

# 素材加载状态标记
_loaded = False


def _load_img(path: Path, scale: Optional[tuple] = None) -> pygame.Surface:
    """加载单张 PNG 图片，可选缩放。"""
    surf = pygame.image.load(str(path)).convert_alpha()
    if scale is not None:
        surf = pygame.transform.smoothscale(surf, scale)
    return surf


def _load_folder(folder_name: str) -> Dict[str, pygame.Surface]:
    """加载指定文件夹下所有 PNG 文件。

    Returns:
        {file_stem: Surface} 字典，文件夹不存在或为空时返回空字典
    """
    folder = ASSET_ROOT / folder_name
    cache: Dict[str, pygame.Surface] = {}
    if not folder.exists():
        logger.debug(f"素材文件夹不存在: {folder}")
        return cache
    for file in folder.glob("*.png"):
        try:
            cache[file.stem] = _load_img(file)
            logger.debug(f"加载素材: {file.name}")
        except Exception as e:
            logger.warning(f"加载素材失败 {file}: {e}")
    logger.info(f"素材文件夹 {folder_name}: 加载 {len(cache)} 张图片")
    return cache


def _load_folder_path(folder: Path) -> Dict[str, pygame.Surface]:
    """加载指定路径文件夹下所有 PNG 文件（支持非ASSET_ROOT目录）。"""
    cache: Dict[str, pygame.Surface] = {}
    if not folder.exists():
        logger.debug(f"素材文件夹不存在: {folder}")
        return cache
    for file in folder.glob("*.png"):
        try:
            cache[file.stem] = _load_img(file)
            logger.debug(f"加载素材: {file.name}")
        except Exception as e:
            logger.warning(f"加载素材失败 {file}: {e}")
    logger.info(f"素材文件夹 {folder}: 加载 {len(cache)} 张图片")
    return cache


def init_all_assets() -> None:
    """程序启动时调用，加载所有素材文件夹（含多套兵种图标）。"""
    global _loaded
    if _loaded:
        return

    # 原有资源
    for folder in ("bg", "ui_btn", "ui_panel", "sheets"):
        _assets[folder] = _load_folder(folder)

    # 新增三套图片素材
    _assets["ui_terrain_img"] = _load_folder("ui_terrain_img")
    _assets["troop_icon_img"] = _load_folder("troop_icon_img")
    _assets["star_icon_img"] = _load_folder("star_icon_img")

    # 预加载所有已注册样式的兵种图标到独立缓存
    _preload_troop_styles()

    _loaded = True
    total = sum(len(v) for v in _assets.values())
    style_total = sum(len(v) for v in _troop_style_cache.values())
    logger.info(f"全部素材加载完成: {total} 张图片, 兵种样式缓存: {style_total} 张")


def _preload_troop_styles() -> None:
    """预加载所有已注册样式的兵种图标到 _troop_style_cache。

    样式数量和目录由 styles_registry.STYLE_REGISTRY 驱动。
    支持每个样式的 extra_folders 字段：主目录优先，额外目录补充缺失素材。
    """
    from .styles_registry import STYLE_REGISTRY

    for style_id, info in STYLE_REGISTRY.items():
        folder = info["folder"]
        # 先加载主目录
        cache = _load_folder_path(folder)
        # 再从额外目录补充（主目录已有的素材优先，不覆盖）
        for extra_folder in info.get("extra_folders", []):
            extra_cache = _load_folder_path(extra_folder)
            for key, surf in extra_cache.items():
                if key not in cache:
                    cache[key] = surf
        _troop_style_cache[style_id] = cache


# ─── 快捷取图函数 ──────────────────────────────────────────

def get_terrain_img(ter_key: str) -> Optional[pygame.Surface]:
    """获取地形原图，不存在返回 None。"""
    return _assets.get("ui_terrain_img", {}).get(ter_key)


def get_troop_img(troop_key) -> Optional[pygame.Surface]:
    """获取士兵原图（当前样式），troop_key 支持数字/字符串，不存在返回 None。"""
    from .style_cache import get_current_icon_style, get_troop_img_filename
    style_id = get_current_icon_style()
    filename = get_troop_img_filename(troop_key, style_id)
    return _troop_style_cache.get(style_id, {}).get(filename)


def get_troop_img_by_style(troop_key, style_id: int) -> Optional[pygame.Surface]:
    """获取指定样式的士兵原图，不存在返回 None。"""
    from .style_cache import get_troop_img_filename
    filename = get_troop_img_filename(troop_key, style_id)
    return _troop_style_cache.get(style_id, {}).get(filename)


def get_star_img(state: str) -> Optional[pygame.Surface]:
    """获取星星图标，state: gray / red / blue，不存在返回 None。"""
    return _assets.get("star_icon_img", {}).get(f"star_{state}")


def has_terrain_imgs() -> bool:
    """是否有地形 PNG 素材。"""
    return len(_assets.get("ui_terrain_img", {})) > 0


def has_troop_imgs() -> bool:
    """是否有士兵 PNG 素材（当前样式）。"""
    from .style_cache import get_current_icon_style
    style_id = get_current_icon_style()
    return len(_troop_style_cache.get(style_id, {})) > 0


def has_star_imgs() -> bool:
    """是否有星星 PNG 素材。"""
    return len(_assets.get("star_icon_img", {})) > 0