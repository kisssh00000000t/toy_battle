"""游戏配置读取（核心层，不依赖UI）。"""
import json
from pathlib import Path

_EXPANSION_CONFIG_PATH = Path(__file__).parent.parent / "expansion_config.json"


def is_expansion_enabled() -> bool:
    """读取扩展包开关状态，默认关闭。"""
    try:
        if _EXPANSION_CONFIG_PATH.exists():
            with open(_EXPANSION_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("enabled", False)
    except Exception:
        pass
    return False


def set_expansion_enabled(enabled: bool) -> None:
    """持久化扩展包开关状态。"""
    try:
        with open(_EXPANSION_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"enabled": bool(enabled)}, f)
    except Exception:
        pass