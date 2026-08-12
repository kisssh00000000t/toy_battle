"""
标准化命令模型（Command Layer）。

所有影响对局状态的行为统一封装为 GameCommand，
确保跨端可序列化、可校验、可追溯。

核心类：
    GameCommand: 标准化确定性行动指令
    DeterministicRNG: 同源确定性随机封装（Phase 3+ 启用）
    WatchdogSyncTimer: 辅机看门狗超时救急（Phase 3+ 启用）
"""

import hashlib
import json
import random
import time
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── 异常定义 ────────────────────────────────────────────────

class SequenceDesyncError(Exception):
    """序列号脱节异常：收到非期望 seq_id 的指令。"""
    pass


class StateHashMismatchError(Exception):
    """状态签名不匹配异常：回放/同步时检测到状态偏差。"""
    pass


# ─── 标准化指令数据结构 ──────────────────────────────────────

class GameCommand:
    """玩具大乱斗 - 标准化确定性行动指令。

    每条网络同步和回放记录中的指令，必须包含以下标准化字段，
    确保跨端可复现、可校验、可追溯。

    Attributes:
        action_type: 指令类型 (DRAW_CARD | PLAY_PIECE | END_TURN | SELECT_TARGET | SYNC_INIT)
        source_player: 发起方 ID: 'red', 'blue' 或 'system'
        payload: 指令具体参数（必须严格确切，不允许传模糊参考）
        seq_id: 严格递增序列号（本地创建默认 -1，由 Dispatcher 赋值）
        random_seed: 若此操作触发随机事件，由主机赋予确定性种子
        timestamp: 毫秒级时间戳
    """

    def __init__(self, action_type: str, source_player: str,
                 payload: Optional[Dict[str, Any]] = None,
                 seq_id: int = -1,
                 random_seed: Optional[int] = None):
        self.action_type = action_type        # DRAW_CARD | PLAY_PIECE | END_TURN | SELECT_TARGET | SYNC_INIT
        self.source_player = source_player    # "red" | "blue" | "system"
        self.payload = payload or {}          # 参数 (如 {"troop_key": 3, "node_id": 14})
        self.seq_id = seq_id                  # 严格递增序列号
        self.random_seed = random_seed        # 随机事件同步种子
        self.timestamp = int(time.time() * 1000)

    def to_dict(self) -> dict:
        """序列化为字典（用于网络传输/回放存储）。"""
        return {
            "seq_id": self.seq_id,
            "action_type": self.action_type,
            "source_player": self.source_player,
            "payload": self.payload,
            "random_seed": self.random_seed,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameCommand":
        """从字典反序列化。"""
        cmd = cls(
            action_type=data["action_type"],
            source_player=data["source_player"],
            payload=data.get("payload", {}),
            seq_id=data.get("seq_id", -1),
            random_seed=data.get("random_seed"),
        )
        cmd.timestamp = data.get("timestamp", int(time.time() * 1000))
        return cmd

    def __repr__(self) -> str:
        return (
            f"<GameCommand seq={self.seq_id} type={self.action_type} "
            f"player={self.source_player}>"
        )


# ─── 确定性随机封装（Phase 3+ 启用）──────────────────────────

class DeterministicRNG:
    """同源确定性随机数生成器。

    全盘禁止客户端和 UI 代码调用原生 random 模块，
    必须通过此实例进行所有随机操作，确保跨端可复现。
    """

    def __init__(self, seed: int):
        self.seed = seed
        self._rng = random.Random(seed)

    def next_int(self, min_val: int, max_val: int) -> int:
        return self._rng.randint(min_val, max_val)

    def next_float(self) -> float:
        return self._rng.random()

    def shuffle(self, lst: list) -> None:
        self._rng.shuffle(lst)

    def choice(self, lst: list) -> Any:
        return self._rng.choice(lst)

    def random(self) -> float:
        """返回 [0.0, 1.0) 区间随机浮点数（等同于 random.random()）。"""
        return self._rng.random()

    def sample(self, population: list, k: int) -> list:
        """从 population 中无放回抽取 k 个元素。"""
        return self._rng.sample(population, k)

    def to_dict(self) -> dict:
        return {"seed": self.seed, "state": self._rng.getstate()}

    @classmethod
    def from_dict(cls, data: dict) -> "DeterministicRNG":
        rng_obj = cls(data["seed"])
        if "state" in data:
            rng_obj._rng.setstate(data["state"])
        return rng_obj


# ─── 状态特征码计算（Phase 4+ 启用）──────────────────────────

def compute_state_hash(game_state) -> str:
    """计算当前对局状态的特征码（MD5 前8位）。"""
    red_hand = sorted([t.troop_key for t in game_state.red.hand])
    blue_hand = sorted([t.troop_key for t in game_state.blue.hand])
    red_reserve = sorted([t.troop_key for t in game_state.red.reserve])
    blue_reserve = sorted([t.troop_key for t in game_state.blue.reserve])

    board_state = []
    for nid in sorted(game_state.board.nodes.keys()):
        node = game_state.board.nodes[nid]
        top_key = node.top_troop.troop_key if node.top_troop else "none"
        top_owner = node.top_troop.owner if node.top_troop else "none"
        stack_size = len(node.stack)
        board_state.append(f"{nid}:{top_owner}:{top_key}:{stack_size}")

    state_payload = {
        "red_hand": red_hand, "blue_hand": blue_hand,
        "red_reserve": red_reserve, "blue_reserve": blue_reserve,
        "board": board_state,
        "red_stars": game_state.red.star_points,
        "blue_stars": game_state.blue.star_points,
        "current_player": game_state.current_player_color,
        "extra_place_pending": game_state.extra_place_pending,
        "turn_place_count": game_state.turn_place_count,
    }
    raw_str = json.dumps(state_payload, sort_keys=True)
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()[:8]


# ─── 网络同步看门狗（Phase 3+ 启用）──────────────────────────

class WatchdogSyncTimer:
    """辅机看门狗超时救急计时器。"""

    MAX_RETRIES = 3

    def __init__(self, timeout_sec: float = 3.5):
        self.timeout_sec = timeout_sec
        self.timer = 0.0
        self.is_waiting = False
        self.retry_count = 0

    def start_waiting(self) -> None:
        self.timer = 0.0
        self.is_waiting = True
        self.retry_count = 0

    def stop_waiting(self) -> None:
        self.is_waiting = False
        self.timer = 0.0
        self.retry_count = 0

    def update(self, dt: float, send_resync_func: Callable) -> bool:
        if not self.is_waiting:
            return False
        self.timer += dt
        if self.timer >= self.timeout_sec:
            if self.retry_count < self.MAX_RETRIES:
                logger.warning(
                    f"同步等待超时 ({self.timer:.1f}s)，"
                    f"发起第 {self.retry_count + 1} 次重同步请求"
                )
                send_resync_func()
                self.retry_count += 1
                self.timer = 0.0
                return True
            else:
                logger.error("同步等待超时且已达最大重试次数，强制关闭等待遮罩")
                self.is_waiting = False
                return False
        return False