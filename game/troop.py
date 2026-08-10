"""
兵种类定义。

每个 Troop 实例代表一枚具体的兵种单位，包含类型、归属和状态。
"""

from .constants import TROOP_DATA


class Troop:
    """兵种单位。

    Attributes:
        troop_key: 兵种标识（"joker" 或 1-7 整数）
        owner: 所属玩家颜色（"red" / "blue"）
        data: 兵种配置字典引用
        is_facedown: 是否面朝下（备用堆/弃牌堆中为 True，手牌/场上为 False）
    """

    def __init__(self, troop_key, owner: str):
        self.troop_key = troop_key
        self.owner = owner
        self.data = TROOP_DATA[troop_key]
        self.is_facedown = True

    @property
    def symbol(self) -> str:
        """兵种显示符号。"""
        return self.data["symbol"]

    @property
    def number(self) -> int | None:
        """兵种数值，Joker 返回 None。"""
        return self.data.get("num")

    @property
    def name(self) -> str:
        """兵种名称。"""
        return self.data["name"]

    @property
    def alias(self) -> str:
        """兵种英文别名。"""
        return self.data["alias"]

    def __repr__(self) -> str:
        return f"<Troop {self.data['alias']} owner={self.owner}>"