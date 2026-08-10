"""
回放系统：基于 action_log 驱动独立 GameState 实例逐步重放。

核心类：
    ReplayEngine: 回放引擎，管理回放状态和步进控制
    ReplayState: 回放状态枚举（PLAYING/PAUSED/FINISHED）
    ReplayPlayer: 战报播放器，从 JSON 文件加载并重放
    export_replay: 导出对局战报到 JSON 文件

使用方式：
    # 引擎模式（内存 action_log）
    engine = ReplayEngine(map_data, action_log)
    engine.start()
    while engine.state != ReplayState.FINISHED:
        engine.step()
        engine.get_snapshot()

    # 战报文件模式
    export_replay(game_state, map_id, "replay.json")
    player = ReplayPlayer("replay.json")
    player.step_forward()
"""

import json
import logging
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from .game_logic import GameState

logger = logging.getLogger(__name__)


# ─── 战报导出 ────────────────────────────────────────────────

def export_replay(game_state: GameState, map_source: str, filepath: str | Path):
    """导出标准确定性战报（固化开局地图拓扑、首发手牌序列与规范指令流）。"""
    
    # 提取最初或当前的标准化牌堆标识流，以备重置还原
    def _extract_deck(player):
        return [t.troop_key for t in player.reserve]

    replay_data = {
        "version": "2.0",
        "map_source": str(map_source),
        "winner": game_state.winner,
        "star_win_goal": game_state.star_win_goal,
        "first_player": getattr(game_state, "first_player", "red"),
        # 【核心修复】：必须使用 to_dict() 完整保存当前真正对战的那幅全真地图
        "map_data": game_state.board.to_dict(),
        "initial_decks": {
            "red": _extract_deck(game_state.red),
            "blue": _extract_deck(game_state.blue),
        },
        "action_log": game_state.action_log,
    }
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(replay_data, f, ensure_ascii=False, indent=2)
    logger.info(f"\u2713 标准确定性战报已写入保存: {path}")


# ─── 回放状态枚举 ────────────────────────────────────────────

class ReplayState(Enum):
    """回放状态枚举。"""
    READY = auto()       # 初始化完成，未开始
    PLAYING = auto()     # 正在播放
    PAUSED = auto()      # 暂停
    FINISHED = auto()    # 播放完毕


# ─── 回放引擎（内存 action_log 驱动）────────────────────────

class ReplayEngine:
    """回放引擎：基于 action_log 驱动独立 GameState 实例。

    特性：
    - 独立 GameState 实例，不影响原对局
    - 支持逐步回放、跳转、暂停/继续
    - 提供 action_log 索引和当前游戏快照

    Attributes:
        game: 当前回放 GameState 实例
        state: 回放状态 (ReplayState)
        log: 原始 action_log
        current_index: 当前回放到的动作索引
    """

    def __init__(self, map_data: dict, action_log: list[dict]):
        """初始化回放引擎。

        Args:
            map_data: 地图数据字典（含 nodes/edges/hq_red/hq_blue/star_points 等）
            action_log: 操作日志列表，每项含 type/player/data
        """
        self._map_data = map_data
        self.log = list(action_log)  # 拷贝，防止修改原日志
        self.current_index = -1
        self.state = ReplayState.READY
        self.game: Optional[GameState] = None
        self._step_callbacks: list = []

    def start(self) -> None:
        """启动回放：创建独立 GameState 并加载地图。"""
        self.game = GameState()
        self.game.board.load_from_dict(self._map_data)
        self.current_index = -1
        self.state = ReplayState.PLAYING

    def step(self) -> Optional[dict]:
        """执行下一步回放动作。

        Returns:
            执行的动作字典，若已结束返回 None
        """
        if self.state == ReplayState.FINISHED:
            return None
        if self.game is None:
            self.start()

        self.current_index += 1
        if self.current_index >= len(self.log):
            self.state = ReplayState.FINISHED
            return None

        action = self.log[self.current_index]
        self._execute_action(action)

        # 通知回调
        for cb in self._step_callbacks:
            cb(action)

        return action

    def step_back(self) -> Optional[dict]:
        """回退一步：从头重放到 current_index - 1。

        注意：由于 GameState 不支持撤销，需要从头重建。

        Returns:
            回退后当前动作字典，若已在开头返回 None
        """
        if self.current_index <= 0:
            return None

        # 从头重建到 current_index - 1
        target = self.current_index - 1
        self.game = GameState()
        self.game.board.load_from_dict(self._map_data)
        self.current_index = -1
        self.state = ReplayState.PLAYING

        for _ in range(target + 1):
            result = self.step()
            if result is None:
                break

        return result

    def jump_to(self, index: int) -> Optional[dict]:
        """跳转到指定动作索引。

        Args:
            index: 目标动作索引（0-based）

        Returns:
            跳转后当前动作字典
        """
        if index < 0 or index >= len(self.log):
            return None

        # 从头重建到目标索引
        self.game = GameState()
        self.game.board.load_from_dict(self._map_data)
        self.current_index = -1
        self.state = ReplayState.PLAYING

        result = None
        for _ in range(index + 1):
            result = self.step()
            if result is None:
                break

        return result

    def pause(self) -> None:
        """暂停回放。"""
        if self.state == ReplayState.PLAYING:
            self.state = ReplayState.PAUSED

    def resume(self) -> None:
        """继续回放。"""
        if self.state == ReplayState.PAUSED:
            self.state = ReplayState.PLAYING

    def on_step(self, callback) -> None:
        """注册步进回调，每次 step() 执行后调用。

        Args:
            callback: 回调函数，接收 action 字典参数
        """
        self._step_callbacks.append(callback)

    @property
    def total_actions(self) -> int:
        """总动作数。"""
        return len(self.log)

    @property
    def progress(self) -> float:
        """回放进度（0.0~1.0）。"""
        if not self.log:
            return 1.0
        return (self.current_index + 1) / len(self.log)

    def get_snapshot(self) -> Optional[dict]:
        """获取当前游戏快照摘要。

        Returns:
            快照字典含 board_state/players/winner/game_over
        """
        if self.game is None:
            return None
        return {
            "current_player": self.game.current_player_color,
            "red_hand_size": len(self.game.red.hand),
            "blue_hand_size": len(self.game.blue.hand),
            "red_star_points": self.game.red.star_points,
            "blue_star_points": self.game.blue.star_points,
            "winner": self.game.winner,
            "game_over": self.game.game_over,
        }

    def _execute_action(self, action: dict) -> None:
        """在回放 GameState 上执行单个动作。

        Args:
            action: 动作字典，含 type/player/data
        """
        atype = action.get("type")
        data = action.get("data", {})
        player_color = data.get("player", action.get("player", "red"))

        if atype == "draw":
            # 抽卡动作：直接调用 draw_cards_action
            self.game.current_player_color = player_color
            self.game.draw_cards_action()

        elif atype == "place":
            # 放置动作：优先 troop_key 精确匹配，回退兼容旧 str(t) 格式
            target_key = data.get("troop_key")
            node_nid = data.get("node") or data.get("node_id")
            if node_nid is not None:
                node = self.game.board.get_node(node_nid)
                if node is not None:
                    self.game.current_player_color = player_color
                    cp = self.game.current_player
                    target_troop = None

                    # 1. 严格 troop_key 匹配（确定性回放）
                    if target_key is not None:
                        for t in cp.hand:
                            if t.troop_key == target_key:
                                target_troop = t
                                break

                    # 2. 兼容旧版无 troop_key 的历史战报
                    if target_troop is None:
                        troop_str = str(data.get("troop", ""))
                        for t in cp.hand:
                            if (str(t.troop_key) in troop_str
                                    or t.alias in troop_str
                                    or t.name in troop_str
                                    or str(t) == troop_str):
                                target_troop = t
                                break

                    # 3. 无损复原容错兜底：动态为当前阵营实例化替补合法棋子
                    if target_troop is None and target_key is not None:
                        from .troop import Troop
                        target_troop = Troop(target_key, cp.color)
                        logger.warning(
                            f"回放步骤 troop_key={target_key} 手牌未命中，"
                            f"已为 [{player_color}] 自动生成补充战棋"
                        )

                    if target_troop:
                        self.game.place_troop(target_troop, node)


# ─── 战报播放器（从 JSON 文件加载）──────────────────────────

class ReplayPlayer:
    """战报播放器：从 JSON 文件加载并逐步重放对局。

    特性：
    - 从 export_replay 导出的 JSON 文件加载
    - 支持逐步前进、快进/跳退到指定步骤
    - 提供当前 GameState 快照
    """

    def __init__(self, replay_path: str | Path):
        """加载战报文件。

        Args:
            replay_path: 战报 JSON 文件路径
        """
        with open(replay_path, "r", encoding="utf-8") as f:
            self.replay_data = json.load(f)

        self.action_log = self.replay_data.get("action_log", [])
        self.cursor = 0

        # 构建并初始化空白状态
        self.game = GameState()
        self._init_game()
        # 将操作记录清空，通过手动推播执行
        self.game.action_log.clear()

    def _init_game(self) -> None:
        """根据战报数据初始化 GameState：优先从 map_data 恢复，确定性初始化牌堆。"""
        from .map_loader import load_map, MapLoader
        from .troop import Troop

        # 1. 优先从战报固化的 map_data 恢复真实对战地图
        if "map_data" in self.replay_data and self.replay_data["map_data"]:
            self.game.board.load_from_dict(self.replay_data["map_data"])
        else:
            # 2. 兼容老版本无 map_data 的战报
            map_src = self.replay_data.get("map_source", "random")
            loaded = False
            if map_src and str(map_src) not in ("random", "custom", "custom_map"):
                try:
                    mp = Path(map_src)
                    if mp.exists():
                        mdata = MapLoader.load_json(mp)
                        self.game.board.load_from_dict(mdata)
                        loaded = True
                except Exception:
                    pass
            if not loaded:
                random_map = load_map()
                self.game.board.load_from_dict(random_map)

        # 3. 确定性初始化：使用 initial_decks + first_player
        initial_decks = self.replay_data.get("initial_decks")
        first_player = self.replay_data.get("first_player")
        if initial_decks and first_player:
            for color in ("red", "blue"):
                player = self.game.red if color == "red" else self.game.blue
                keys = initial_decks.get(color, [])
                player.reserve = [Troop(k, color) for k in keys]
            self.game.current_player_color = first_player
            self.game.first_player = first_player
            self.game.initial_decks = initial_decks
            if first_player == "red":
                self.game.red.init_draw(True)
                self.game.blue.init_draw(False)
            else:
                self.game.blue.init_draw(True)
                self.game.red.init_draw(False)
        else:
            self.game.setup()

    @property
    def is_finished(self) -> bool:
        """是否已播放完毕。"""
        return self.cursor >= len(self.action_log)

    @property
    def total_steps(self) -> int:
        """总步骤数。"""
        return len(self.action_log)

    @property
    def current_step(self) -> int:
        """当前步骤索引。"""
        return self.cursor

    def step_forward(self) -> bool:
        """向后回放一步操作。

        Returns:
            是否成功执行
        """
        if self.is_finished:
            return False

        action = self.action_log[self.cursor]
        act_type = action.get("type")
        data = action.get("data", {})
        player_color = data.get("player", action.get("player", "red"))

        if act_type == "draw":
            self.game.current_player_color = player_color
            self.game.draw_cards_action()
        elif act_type == "place":
            nid = data.get("node") or data.get("node_id")
            node = self.game.board.get_node(nid) if nid is not None else None
            if node:
                self.game.current_player_color = player_color
                cp = self.game.current_player
                target_key = data.get("troop_key")
                target_troop = None

                # 1. 严格 troop_key 匹配
                if target_key is not None:
                    for t in cp.hand:
                        if t.troop_key == target_key:
                            target_troop = t
                            break

                # 2. 兼容旧版战报
                if target_troop is None:
                    troop_str = str(data.get("troop", ""))
                    for t in cp.hand:
                        if (str(t.troop_key) in troop_str
                                or t.alias in troop_str
                                or t.name in troop_str
                                or str(t) == troop_str):
                            target_troop = t
                            break

                # 3. 无损复原容错兜底
                if target_troop is None and target_key is not None:
                    from .troop import Troop
                    target_troop = Troop(target_key, cp.color)
                    logger.warning(
                        f"ReplayPlayer 步骤 {self.cursor}: troop_key={target_key} "
                        f"手牌未命中，已自动生成补充战棋"
                    )

                if target_troop:
                    self.game.place_troop(target_troop, node)

        # 当前步骤做完后尝试推进回合
        if (not self.game.extra_place_pending
                and self.game.turn_place_count > 0):
            self.game.end_turn()

        self.cursor += 1
        return True

    def reset_and_play_to(self, step_idx: int) -> None:
        """快进/跳退到指定的步骤下标。

        Args:
            step_idx: 目标步骤索引（0-based）
        """
        self.cursor = 0
        self._init_game()
        self.game.action_log.clear()
        while self.cursor < min(step_idx, len(self.action_log)):
            self.step_forward()