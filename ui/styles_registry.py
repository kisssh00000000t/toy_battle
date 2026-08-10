"""
图标样式注册表 — 开放式样式管理。

替代 style_cache.py 中的硬编码双样式映射，
采用注册表模式支持任意数量的图标样式扩展。

使用方式：
  from .styles_registry import STYLE_REGISTRY, get_all_styles, get_troop_filename

注册新样式只需在 STYLE_REGISTRY 中添加一条记录即可，
无需修改 style_cache / asset_loader / settings_screen 等下游代码。
"""

import logging
from collections import OrderedDict
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── 素材根目录 ──────────────────────────────────────────
ASSET_ROOT = Path(__file__).parent.parent / "assets"
CUT_ROOT = Path(__file__).parent.parent / "cut"

# ═══════════════════════════════════════════════════════════
#  样式注册表
# ═══════════════════════════════════════════════════════════
#  每条记录包含：
#    name   : 样式显示名称（用于UI按钮）
#    folder : 主素材目录路径
#    extra_folders : (可选) 额外素材目录列表，主目录优先，额外目录补充缺失素材
#    troop_filenames : {troop_key: filename_stem} 映射
#                      troop_key 与 TROOP_DATA 的 key 一致：("joker", 1, 2, ..., 17)
#                      filename_stem 为不含 .png 后缀的文件名

STYLE_REGISTRY: OrderedDict[int, dict] = OrderedDict([
    (1, {
        "name": "经典",
        "folder": ASSET_ROOT / "troop_icon_img",
        "troop_filenames": {
            "joker": "joker",
            1: "troop_1",
            2: "troop_2",
            3: "troop_3",
            4: "troop_4",
            5: "troop_5",
            6: "troop_6",
            7: "troop_7",
            # --- 扩展兵种 8~17（占位符，素材待补充）---
            8: "troop_8",
            9: "troop_9",
            10: "troop_10",
            11: "troop_11",
            12: "troop_12",
            13: "troop_13",
            14: "troop_14",
            15: "troop_15",
            16: "troop_16",
            17: "troop_17",
        },
    }),
    (2, {
        "name": "新版",
        "folder": CUT_ROOT / "new1",
        "troop_filenames": {
            "joker": "troop_joker_duck",
            1: "troop_skeleton",
            2: "troop_captain",
            3: "troop_knight",
            4: "troop_hook_pirate",
            5: "troop_xb42",
            6: "troop_unicorn_star",
            7: "troop_roxy_dino",
            # --- 扩展兵种 8~17（占位符，素材待补充）---
            8: "troop_8",
            9: "troop_9",
            10: "troop_10",
            11: "troop_11",
            12: "troop_12",
            13: "troop_13",
            14: "troop_14",
            15: "troop_15",
            16: "troop_16",
            17: "troop_17",
        },
    }),
    (3, {
        "name": "卡通",
        "folder": CUT_ROOT / "new2",
        "extra_folders": [CUT_ROOT / "new3"],  # 扩展兵种 8~17 从 new3 加载
        "troop_filenames": {
            "joker": "troop_joker_duck",
            1: "troop_skeleton",
            2: "troop_captain",
            3: "troop_knight",
            4: "troop_hook_pirate",
            5: "troop_xb42",
            6: "troop_unicorn_star",
            7: "troop_roxy_dino",
            # --- 扩展兵种 8~17（cut/new3 实际素材）---
            8: "troop_8",
            9: "troop_9",
            10: "troop_10",
            11: "troop_11",
            12: "troop_12",
            13: "troop_13",
            14: "troop_14",
            15: "troop_15",
            16: "troop_16",
            17: "troop_17",
        },
    }),
])


# ═══════════════════════════════════════════════════════════
#  查询接口
# ═══════════════════════════════════════════════════════════

def get_all_styles() -> list[int]:
    """返回所有已注册的样式ID列表。"""
    return list(STYLE_REGISTRY.keys())


def get_style_info(style_id: int) -> dict:
    """获取指定样式的完整信息，不存在返回 None。"""
    return STYLE_REGISTRY.get(style_id)


def get_style_name(style_id: int) -> str:
    """获取样式显示名称，不存在返回 '未知样式'。"""
    info = STYLE_REGISTRY.get(style_id)
    return info["name"] if info else "未知样式"


def get_style_folder(style_id: int) -> Path:
    """获取样式素材目录，不存在返回 ASSET_ROOT。"""
    info = STYLE_REGISTRY.get(style_id)
    return info["folder"] if info else ASSET_ROOT


def get_troop_filename(troop_key, style_id: int) -> str:
    """根据兵种key + 样式ID获取图片文件名（不含.png后缀）。

    Args:
        troop_key: 兵种key（"joker" / 1~7）
        style_id: 样式编号

    Returns:
        文件名stem，未找到返回 str(troop_key)
    """
    info = STYLE_REGISTRY.get(style_id)
    if info is None:
        logger.warning(f"未知样式ID: {style_id}")
        return str(troop_key)
    filename = info["troop_filenames"].get(troop_key)
    if filename is None:
        logger.warning(f"样式{style_id}中未找到兵种key: {troop_key}")
        return str(troop_key)
    return filename


def validate_all_styles() -> list[str]:
    """校验所有已注册样式的素材完整性。

    Returns:
        错误信息列表，空列表表示全部校验通过
    """
    errors = []
    for style_id, info in STYLE_REGISTRY.items():
        folder = info["folder"]
        # 收集所有可搜索目录：主目录 + 额外目录
        search_folders = [folder] + info.get("extra_folders", [])
        for troop_key, filename in info["troop_filenames"].items():
            # 在所有目录中查找，任一目录存在即视为通过
            found = any((f / f"{filename}.png").exists() for f in search_folders)
            if not found:
                errors.append(f"样式{style_id}({info['name']}) 缺失: {filename}.png (搜索目录: {[str(f) for f in search_folders]})")
    return errors