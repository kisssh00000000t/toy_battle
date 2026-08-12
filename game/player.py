"""
玩家资源管理模块。

管理手牌、备用堆、弃牌堆、封存区和勋章。
"""

import random
from .troop import Troop
from .constants import TROOP_DATA, HAND_MAX, REMOVE_COUNT_PER_GAME, INIT_DRAW_FIRST, INIT_DRAW_SECOND


class Player:
    """玩家资源管理器。

    Attributes:
        color: 玩家颜色标识（"red" / "blue"）
        reserve: 备用堆（面朝下的牌堆）
        hand: 手牌（面朝上的可用牌）
        discard: 弃牌堆
        star_points: 已获得星星总数
        captured_areas: 已占领区块ID集合
        sealed_troop: 本回合被封存的兵种（古战场效果）
    """

    def __init__(self, color: str):
        self.color = color
        self.reserve: list[Troop] = []
        self.hand: list[Troop] = []
        self.discard: list[Troop] = []
        self.star_points = 0
        self.captured_areas: set[int] = set()
        self.sealed_troop: Troop | None = None

    def reset(self) -> None:
        """重置玩家状态（新局开始时调用）。"""
        self.reserve.clear()
        self.hand.clear()
        self.discard.clear()
        self.star_points = 0
        self.captured_areas.clear()
        self.sealed_troop = None

    def setup_troops(self, troop_keys=None, rng=None) -> None:
        """初始化兵种：每种3枚，随机移除4枚，剩余入备用堆。

        Args:
            troop_keys: 可选的兵种键列表，用于拓展包开关过滤。
                       若为 None 则使用 TROOP_DATA 全部键。
            rng: DeterministicRNG 实例，若提供则使用确定性随机；否则回退到原生 random。
        """
        troops: list[Troop] = []
        keys = troop_keys if troop_keys is not None else list(TROOP_DATA.keys())
        for key in keys:
            for _ in range(3):
                troops.append(Troop(key, self.color))
        if rng is not None:
            rng.shuffle(troops)
        else:
            random.shuffle(troops)
        # 移除4枚（不可用），剩余入备用堆
        removed = troops[:REMOVE_COUNT_PER_GAME]
        self.reserve = troops[REMOVE_COUNT_PER_GAME:]
        if rng is not None:
            rng.shuffle(self.reserve)
        else:
            random.shuffle(self.reserve)

    def draw(self, count: int = 1) -> int:
        """从备用堆抽牌到手牌。

        Args:
            count: 期望抽取数量

        Returns:
            实际抽取数量（受手牌上限和备用堆数量限制）
        """
        got = 0
        for _ in range(count):
            if len(self.hand) >= HAND_MAX or not self.reserve:
                break
            t = self.reserve.pop()
            t.is_facedown = False
            self.hand.append(t)
            got += 1
        return got

    def init_draw(self, is_first: bool) -> None:
        """开局抽牌。

        Args:
            is_first: 是否为先手玩家（先手抽3，后手抽4）
        """
        if is_first:
            self.draw(INIT_DRAW_FIRST)
        else:
            self.draw(INIT_DRAW_SECOND)

    def discard_troop(self, troop: Troop) -> None:
        """将兵种移入弃牌堆。"""
        troop.is_facedown = True
        if troop in self.hand:
            self.hand.remove(troop)
        self.discard.append(troop)

    def return_to_hand(self, troop: Troop) -> bool:
        """从弃牌堆回收兵种到手牌。

        Returns:
            是否成功回收（手牌满则失败）
        """
        if len(self.hand) >= HAND_MAX:
            return False
        troop.is_facedown = False
        if troop in self.discard:
            self.discard.remove(troop)
        self.hand.append(troop)
        return True

    def seal_troop(self, troop: Troop) -> None:
        """封存一张手牌（古战场效果）。"""
        if troop in self.hand:
            self.hand.remove(troop)
            self.sealed_troop = troop

    def unseal_troop(self) -> None:
        """归还封存的手牌（回合结束时调用）。"""
        if not self.sealed_troop:
            return
        if len(self.hand) < HAND_MAX:
            self.sealed_troop.is_facedown = False
            self.hand.append(self.sealed_troop)
        else:
            # 手牌满则进入弃牌堆
            self.discard.append(self.sealed_troop)
        self.sealed_troop = None

    def can_draw(self) -> bool:
        """是否还能抽牌。"""
        return len(self.reserve) > 0 and len(self.hand) < HAND_MAX

    # ─── 序列化 ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        """序列化玩家状态为字典。"""
        return {
            "color": self.color,
            "star_points": self.star_points,
            "captured_areas": list(self.captured_areas),
            "reserve": [t.to_dict() for t in self.reserve],
            "hand": [t.to_dict() for t in self.hand],
            "discard": [t.to_dict() for t in self.discard],
            "sealed_troop": self.sealed_troop.to_dict() if self.sealed_troop else None,
        }

    def from_dict(self, data: dict) -> None:
        """从字典反序列化恢复玩家状态。"""
        self.star_points = data.get("star_points", 0)
        self.captured_areas = set(data.get("captured_areas", []))
        self.reserve = [Troop.from_dict(td) for td in data.get("reserve", [])]
        self.hand = [Troop.from_dict(td) for td in data.get("hand", [])]
        self.discard = [Troop.from_dict(td) for td in data.get("discard", [])]
        st = data.get("sealed_troop")
        self.sealed_troop = Troop.from_dict(st) if st else None

    def __repr__(self) -> str:
        # FIX: 原代码 f"<Player {color} ...>" 引用未定义变量 color
        return f"<Player {self.color} hand:{len(self.hand)} stars:{self.star_points}>"