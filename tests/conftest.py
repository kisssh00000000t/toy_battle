"""测试配置：确保 troop_war_game/ 在 sys.path 中，使绝对导入生效。"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))