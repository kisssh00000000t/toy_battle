"""
兵种类定义。

每个 Troop 实例代表一枚具体的兵种单位，包含类型、归属和状态。
"""

from .constants import TROOP_DATA

_roster_counter = 0


def _next_roster_id() -> int:
    global _roster_counter
    _roster_counter += 1
    return _roster_counter


class Troop:
    """兵种单位。

    Attributes:
        troop_key: 兵种标识（"joker" 或 1-7 整数）
        owner: 所属玩家颜色（"red" / "blue"）
        data: 兵种配置字典引用
        is_facedown: 是否面朝下（备用堆/弃牌堆中为 True，手牌/场上为 False）
        roster_id: 实例级唯一ID，支持弃牌堆精确选择
    """

    def __init__(self, troop_key, owner: str, roster_id: int | None = None):
        self.troop_key = troop_key
        self.owner = owner
        self.data = TROOP_DATA[troop_key]
        self.is_facedown = True
        self.roster_id = roster_id if roster_id is not None else _next_roster_id()

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

    def to_dict(self) -> dict:
        return {
            "troop_key": self.troop_key,
            "owner": self.owner,
            "is_facedown": self.is_facedown,
            "roster_id": self.roster_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Troop":
        t = cls(data["troop_key"], data["owner"], roster_id=data.get("roster_id"))
        t.is_facedown = data.get("is_facedown", True)
        return t

    def __repr__(self) -> str:
        return f"<Troop {self.data['alias']} owner={self.owner} rid={self.roster_id}>"