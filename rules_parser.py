"""
规则文档生成器 - 从常量配置自动生成电子版玩法手册。

用法:
    python -m troop_war_game.rules_parser
"""

from pathlib import Path
from .game.constants import TROOP_DATA, TERRAIN_DATA

RULE_MD = """# TroopWar 电子版完整玩法简介
## 游戏目标
1. 将任意兵种放置到敌方总部，立即获胜
2. 收集地图指定数量勋章，立即获胜
平局判定：双方无人达成即时胜利，但无法继续操作
勋章数更多一方获胜；勋章相同，本轮行动失败方落败

## 游戏设置
1. 基础8类兵种（Joker + 1~7号），每种3枚，每人初始24枚
2. 扩展10类兵种（8~17号），每种按配置数量提供
3. 本局随机移除4枚基础兵种，每人可用20枚基础兵种
4. 随机先手：先手初始抽3，后手抽4

## 回合操作（二选一）
### A 抽卡
手牌≤6抽2，手牌7仅抽1；手牌上限8
抽卡后直接结束回合
### B 放置兵种
1. 从手牌选中兵种，点击地图节点放置
2. 放置前置校验：连通、地形、覆盖规则
3. 放置成功后：
   1）覆盖敌方单位执行销毁逻辑
   2）执行兵种效果（金属X站跳过）
   3）执行地形效果
   4）检测区域勋章
   5）检测即时胜利
4. 玩具队长可额外放置一次，否则结束回合

## 基础兵种规则（Joker + 1~7号）
"""


def build_rule_doc(output_path: str | Path | None = None) -> Path:
    """生成规则文档。

    Args:
        output_path: 输出文件路径，默认为 docs/rulebook.md

    Returns:
        生成的文件路径
    """
    lines = [RULE_MD]
    lines.append("|编号|名称|符号|效果|\n|---|---|---|---|\n")
    joker = TROOP_DATA["joker"]
    lines.append(f"|J|{joker['alias']} {joker['name']}|{joker['symbol']}|{joker['desc']}|\n")
    for num in range(1, 8):
        t = TROOP_DATA[num]
        lines.append(f"|{num}|{t['alias']} {t['name']}|{t['symbol']}|{t['desc']}|\n")

    # 扩展兵种（8~17号）
    expansion_keys = [k for k in TROOP_DATA if isinstance(k, int) and k >= 8]
    if expansion_keys:
        lines.append("\n## 扩展兵种规则（8~17号）\n\n")
        lines.append("|编号|名称|符号|战力|效果|\n|---|---|---|---|---|\n")
        for num in sorted(expansion_keys):
            t = TROOP_DATA[num]
            lines.append(f"|{num}|{t['alias']} {t['name']}|{t['symbol']}|{t['num']}|{t['desc']}|\n")
    lines.append("\n## 地形规则\n")
    for k, v in TERRAIN_DATA.items():
        lines.append(f"**{v['name']} {v['symbol']}**：{v['desc']}\n\n")

    if output_path is None:
        output_path = Path("docs/rulebook.md")
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(lines), encoding="utf-8")
    print(f"规则文档生成完成：{output_path}")
    return output_path


if __name__ == "__main__":
    build_rule_doc()