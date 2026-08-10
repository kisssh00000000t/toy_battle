"""
玩具大乱斗 - 游戏入口。

用法:
    python -m troop_war_game          # 启动游戏
    python -m troop_war_game --editor # 启动地图编辑器
"""

import sys
import logging
from pathlib import Path

# 将项目根目录添加到 sys.path，确保能导入 ui 等包
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    """主入口。"""
    # 启动自检：校验图标素材完整性
    from ui.style_cache import validate_troop_mapping
    errors = validate_troop_mapping()
    if errors:
        for err in errors:
            logging.warning(f"图标素材校验失败: {err}")

    from ui.manager import ScreenManager
    manager = ScreenManager()
    if "--editor" in sys.argv:
        from ui.editor_screen import EditorScreen
        manager.run(start_screen=EditorScreen)
    else:
        manager.run()


if __name__ == "__main__":
    main()