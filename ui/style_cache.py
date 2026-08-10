"""
图标样式缓存管理 — 样式注册表驱动 + 本地持久化。

管理兵种图标样式的映射关系和用户偏好持久化。
样式注册表在 styles_registry.py 中定义，支持任意数量样式扩展。

切换样式后自动失效 render_cache 中的兵种缓存，触发重新预渲染。
零侵入原则：仅被 ui/ 目录引用，game/ 层不依赖。
"""

import json
import logging
from pathlib import Path

from .styles_registry import (
    STYLE_REGISTRY,
    get_all_styles,
    get_troop_filename as _registry_get_filename,
    validate_all_styles,
)

logger = logging.getLogger(__name__)

# ─── 本地缓存路径 ──────────────────────────────────────────
_CACHE_DIR = Path(__file__).parent.parent / "assets" / "cache"
_CACHE_FILE = _CACHE_DIR / "style_config.json"

# ─── 默认样式 ──────────────────────────────────────────────
DEFAULT_STYLE = 1  # 默认使用样式1（经典图标）

# ─── 向后兼容：保留 TROOP_NAME_MAPPING 供 settings_screen 预览区使用 ──
# 从注册表自动生成，无需手动维护
TROOP_NAME_MAPPING = []
for _sid, _info in STYLE_REGISTRY.items():
    pass  # 仅遍历到最后一条以构建映射

# 构建 TROOP_NAME_MAPPING：以注册表第一个样式为基准 troop_key 列表
_BASE_STYLE = STYLE_REGISTRY[1]
_TROOP_KEYS = list(_BASE_STYLE["troop_filenames"].keys())

TROOP_NAME_MAPPING = []
for _key in _TROOP_KEYS:
    entry = {"troop_key": _key}
    for _sid in STYLE_REGISTRY:
        entry[f"style{_sid}"] = STYLE_REGISTRY[_sid]["troop_filenames"][_key]
    TROOP_NAME_MAPPING.append(entry)

# troop_key → 映射条目的快速查找表
_TROOP_KEY_MAP = {entry["troop_key"]: entry for entry in TROOP_NAME_MAPPING}


# ═══════════════════════════════════════════════════════════
#  持久化读写
# ═══════════════════════════════════════════════════════════

def get_current_icon_style() -> int:
    """读取缓存的图标样式，无缓存或非法值返回默认样式。"""
    if not _CACHE_FILE.exists():
        return DEFAULT_STYLE
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            style = int(data.get("icon_style", DEFAULT_STYLE))
            valid_styles = get_all_styles()
            return style if style in valid_styles else DEFAULT_STYLE
    except Exception as e:
        logger.warning(f"读取样式缓存失败: {e}")
        return DEFAULT_STYLE


def set_current_icon_style(style_id: int) -> None:
    """保存选中样式到本地缓存。

    Args:
        style_id: 样式编号，必须在注册表中存在
    """
    valid_styles = get_all_styles()
    if style_id not in valid_styles:
        logger.warning(f"非法样式编号: {style_id}，已注册样式: {valid_styles}")
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {"icon_style": style_id}
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"图标样式已保存: 样式{style_id}")
    except Exception as e:
        logger.warning(f"保存样式缓存失败: {e}")


# ═══════════════════════════════════════════════════════════
#  映射查询
# ═══════════════════════════════════════════════════════════

def get_troop_img_filename(troop_key, style_id: int = None) -> str:
    """根据兵种key + 样式ID获取图片文件名（不含.png后缀）。

    Args:
        troop_key: 兵种key（"joker" / 1~7）
        style_id: 样式编号，None 则使用当前缓存样式

    Returns:
        文件名（不含后缀），如 "troop_1" 或 "troop_skeleton"
    """
    if style_id is None:
        style_id = get_current_icon_style()
    return _registry_get_filename(troop_key, style_id)


# ═══════════════════════════════════════════════════════════
#  启动自检
# ═══════════════════════════════════════════════════════════

def validate_troop_mapping() -> list:
    """校验所有已注册样式的素材文件全部存在。

    Returns:
        错误信息列表，空列表表示校验通过
    """
    return validate_all_styles()