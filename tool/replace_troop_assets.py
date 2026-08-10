"""
素材替换 + 缓存刷新一键脚本。

功能：
1. 将 cut/ 目录下 8 张兵种图标复制覆盖到 assets/troop_icon_img/
2. 完整删除 assets/cache/ 缓存文件夹
3. 边缘透明像素清理（消除杂边遮挡）
4. 重新加载资源 + 生成磁盘持久缓存

使用方式：
  关闭游戏后执行：python tool/replace_troop_assets.py
"""
import shutil
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ─── 配置 ────────────────────────────────────────────────
SRC_CUT = ROOT / "cut"
DEST_TROOP = ROOT / "assets" / "troop_icon_img"
DEST_TERRAIN = ROOT / "assets" / "ui_terrain_img"
CACHE_FOLDER = ROOT / "assets" / "cache"

TROOP_FILES = [
    "joker.png",
    "troop_1.png",
    "troop_2.png",
    "troop_3.png",
    "troop_4.png",
    "troop_5.png",
    "troop_6.png",
    "troop_7.png",
]

# 地形文件映射：cut/ 文件名 → assets/ 文件名（修正拼写变体）
TERRAIN_MAP = {
    "battlefield.png": "battlefield.png",
    "caribbean_sea.png": "caribbean_sea.png",
    "castle_field.png": "castle_field.png",
    "city_of_cloud.png": "city_of_clouds.png",      # +s
    "curse_cemetery.png": "cursed_cemetery.png",     # curse→cursed
    "nomal.png": "normal.png",                       # nomal→normal
    "station_metalx.png": "station_metalx.png",
    "tropical_pool.png": "tropical_pool.png",
    "volcanic_jungle.png": "volcanic_jungle.png",
}

# 透明度阈值：低于此值的像素强制透明（消除杂边）
ALPHA_THRESH = 12


def clean_edge_transparent(img_path: Path) -> None:
    """对单张 PNG 做边缘透明像素清理，消除半透明杂边。"""
    try:
        from PIL import Image
    except ImportError:
        print(f"  \u26A0 Pillow 未安装，跳过边缘清理: {img_path.name}")
        return

    img = Image.open(img_path).convert("RGBA")
    data = img.getdata()
    cleaned = []
    changed = 0
    for r, g, b, a in data:
        if a < ALPHA_THRESH:
            cleaned.append((0, 0, 0, 0))
            changed += 1
        else:
            cleaned.append((r, g, b, a))
    if changed > 0:
        img.putdata(cleaned)
        img.save(img_path, format="PNG")
        print(f"  \U0001F9F9 边缘清理: {img_path.name} ({changed} 像素)")
    else:
        print(f"  \u2713 边缘干净: {img_path.name}")


def replace_troop_images():
    """执行素材替换 + 缓存刷新。"""
    # 1. 校验源文件
    missing_troop = [f for f in TROOP_FILES if not (SRC_CUT / f).exists()]
    if missing_troop:
        print(f"\u274C cut/ 缺失兵种文件: {missing_troop}")
        return False
    missing_terrain = [f for f in TERRAIN_MAP if not (SRC_CUT / f).exists()]
    if missing_terrain:
        print(f"\u274C cut/ 缺失地形文件: {missing_terrain}")
        return False

    # 2. 确保目标目录存在
    DEST_TROOP.mkdir(parents=True, exist_ok=True)
    DEST_TERRAIN.mkdir(parents=True, exist_ok=True)

    # 3. 覆盖复制兵种图标
    print("\n\U0001F4E6 第1步：复制兵种图标 → assets/troop_icon_img/")
    for fname in TROOP_FILES:
        src = SRC_CUT / fname
        dst = DEST_TROOP / fname
        shutil.copy2(src, dst)
        print(f"  \u2705 {fname}")
    print("  兵种图标替换完成")

    # 4. 覆盖复制地形图标（含文件名修正）
    print("\n\U0001F5FA  第2步：复制地形图标 → assets/ui_terrain_img/")
    for src_name, dst_name in TERRAIN_MAP.items():
        src = SRC_CUT / src_name
        dst = DEST_TERRAIN / dst_name
        shutil.copy2(src, dst)
        tag = " (重命名)" if src_name != dst_name else ""
        print(f"  \u2705 {src_name} → {dst_name}{tag}")
    print("  地形图标替换完成")

    # 5. 边缘透明像素清理
    print("\n\U0001F9F9 第3步：边缘透明像素清理")
    for fname in TROOP_FILES:
        clean_edge_transparent(DEST_TROOP / fname)
    for dst_name in TERRAIN_MAP.values():
        clean_edge_transparent(DEST_TERRAIN / dst_name)

    # 6. 清除全部旧缓存
    print("\n\U0001F5D1  第4步：清除旧缓存")
    if CACHE_FOLDER.exists():
        shutil.rmtree(CACHE_FOLDER)
        print(f"  \u2705 已删除 {CACHE_FOLDER}")
    else:
        print("  \u2713 缓存目录不存在，无需删除")

    # 7. 重新加载资源 + 生成磁盘持久缓存
    print("\n\U0001F504 第5步：重新加载资源 + 生成缓存")
    try:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        pygame.init()
        from ui.asset_loader import init_all_assets
        from ui.render_cache import pre_render_all_icons

        init_all_assets()
        pre_render_all_icons(use_persist_cache=True)
        print("  \u2705 资源重载完成，新缓存已生成")
    except Exception as e:
        print(f"  \u26A0 资源重载跳过（需 pygame 环境）: {e}")
        print("  提示：首次启动游戏时会自动生成缓存")

    print("\n\U0001F389 全部完成！可以启动游戏验证新图标。")
    return True


if __name__ == "__main__":
    replace_troop_images()