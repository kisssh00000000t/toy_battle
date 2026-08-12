"""
AI 机器人模块：贪心策略自动决策。

核心类：
    AIBot: AI 决策机器人，基于贪心评估选择最优操作

策略优先级：
    0. 优先处理二段技能（防卡死，贪心选取高战力敌人）
    1. HQ 夺取（权重 10000）—— 占领对方总部直接获胜
    2. 区域闭合（权重 1000）—— 完成区域占领获得星星
    3. 重装骑士群攻（180/敌）—— 骑士群冲锋高价值目标
    4. 数值覆盖（基础分）—— 战力压制敌方驻军
    5. 地形要冲（权重 50）—— 控制关键连接节点
    6. 抽卡/结束回合 —— 无更好选择时的默认操作
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from .game_logic import GameState
from .board import BoardNode
from .troop import Troop

logger = logging.getLogger(__name__)


class AIBot:
    """AI 决策机器人：基于贪心策略评估并选择最优操作。

    特性：
    - 多维度评分：HQ夺取、区域闭合、战力覆盖、地形要冲
    - 支持二段技能释放、抽卡、放置、结束回合
    - 可配置权重参数调整策略倾向

    使用方式：
        bot = AIBot("red")
        action = bot.decide_action(game_state)
        # action = {"type": "draw"} / {"type": "place", ...} / {"type": "end_turn"}
    """

    # ── 权重常量 ──
    W_HQ_CAPTURE = 10000      # 夺取敌方总部
    W_AREA_CLOSE = 1000       # 完成区域闭合
    W_KNIGHT_PER_ENEMY = 180  # 骑士群攻（每敌兵）
    W_TERRAIN_KEY = 50        # 地形要冲
    W_BASE_OVERLAP = 10       # 基础战力覆盖

    def __init__(self, player_color: str,
                 w_hq: int = W_HQ_CAPTURE,
                 w_area: int = W_AREA_CLOSE,
                 w_knight: int = W_KNIGHT_PER_ENEMY,
                 w_terrain: int = W_TERRAIN_KEY):
        """初始化 AI 机器人。

        Args:
            player_color: 玩家颜色 ("red" / "blue")
            w_hq: HQ夺取权重
            w_area: 区域闭合权重
            w_knight: 骑士群攻权重（每敌兵）
            w_terrain: 地形要冲权重
        """
        self.player_color = player_color
        self.w_hq = w_hq
        self.w_area = w_area
        self.w_knight = w_knight
        self.w_terrain = w_terrain

    def decide_action(self, game: GameState) -> dict:
        """根据当前游戏状态决定最优操作。

        Args:
            game: 当前 GameState

        Returns:
            操作字典，格式：
            - {"type": "draw"} — 抽卡
            - {"type": "place", "troop_key": int, "target_nid": int} — 放置
            - {"type": "end_turn"} — 结束回合
            - {"type": "select", "option_id": ...} — 处理 pending_selection
            - {"type": "cast_skill", "target_nid": ...} — 释放二段技能
        """
        # ── 0a. 处理玩家选择（AI自动选第一个或跳过） ──
        if getattr(game, "pending_selection", None):
            sel = game.pending_selection
            if sel.get("cancellable"):
                return {"type": "select", "option_id": None}
            options = sel.get("options", [])
            if options:
                return {"type": "select", "option_id": options[0]["id"]}
            return {"type": "select", "option_id": None}

        player = game.red if self.player_color == "red" else game.blue
        opponent_color = "blue" if self.player_color == "red" else "red"

        # ── 0b. 优先处理挂起的二段技能（防死锁） ──
        pending = getattr(game, 'pending_skill', None)
        if pending:
            t_key = pending["troop_key"]
            src_nid = pending["source_nid"]
            valid_targets = game.get_skill_target_nodes()
            if valid_targets:
                # 评估每个目标的价值
                best_target = None
                best_score = -1
                for tgt in valid_targets:
                    s = 0
                    if tgt.top_troop:
                        s += (tgt.top_troop.number or 0) * 20
                        # 装甲车(13)高价值目标
                        if tgt.top_troop.troop_key == 13:
                            s += 100
                    if s > best_score:
                        best_score = s
                        best_target = tgt

                target_nid = best_target.nid if best_target else valid_targets[0].nid
                return {"type": "cast_skill", "target_nid": target_nid}
            else:
                # 没有任何合法目标时，发送 None 主动跳过技能
                return {"type": "cast_skill", "target_nid": None}

        # ── 1. 如果手牌为空且可以抽卡，先抽卡 ──
        if not player.hand and player.can_draw():
            return {"type": "draw"}

        # ── 2. 如果手牌为空且不能抽卡，结束回合 ──
        if not player.hand:
            return {"type": "end_turn"}

        # ── 3. 评估每个 (troop, node) 组合的得分 ──
        best_score = -1
        best_action: Optional[dict] = None

        for troop in player.hand:
            valid_nodes = game.get_valid_nodes(troop)
            for node in valid_nodes:
                score = self._evaluate_move(game, troop, node, opponent_color)
                if score > best_score:
                    best_score = score
                    best_action = {
                        "type": "place",
                        "troop_key": troop.troop_key,
                        "target_nid": node.nid,
                    }

        # ── 4. 如果有高价值放置操作，执行 ──
        if best_action is not None and best_score > 0:
            return best_action

        # ── 5. 没有好的放置选择 → 尝试抽卡 ──
        if player.can_draw():
            return {"type": "draw"}

        # ── 6. 无法抽卡 → 结束回合 ──
        return {"type": "end_turn"}

    def _evaluate_move(self, game: GameState, troop: Troop,
                       node: BoardNode, opponent_color: str) -> int:
        """评估在指定节点放置兵种的综合得分。

        Args:
            game: 当前 GameState
            troop: 待放置兵种
            node: 目标节点
            opponent_color: 对手颜色

        Returns:
            综合得分（越高越好）
        """
        score = 0

        # ── 0. 己方HQ排除：不可在己方HQ放置，直接返回0 ──
        if node.is_hq and node.hq_owner == self.player_color:
            return 0

        # ── 1. HQ 夺取 ──
        if node.is_hq and node.hq_owner == opponent_color:
            # 放置在对方总部 → 检查是否能夺取
            score += self.w_hq_capture_if_possible(game, troop, node, opponent_color)

        # ── 2. 区域闭合 ──
        area_close_bonus = self._area_close_bonus(game, node)
        score += area_close_bonus

        # ── 3. 重装骑士群攻 ──
        if troop.troop_key == 3:  # 重装骑士（key==3）
            # 修复：数相邻节点的敌军，而非目标节点堆叠
            neighbor_ids = game.board.get_neighbors(node.nid)
            for nb_nid in neighbor_ids:
                nb = game.board.get_node(nb_nid)
                if nb and nb.top_troop and nb.top_troop.owner == opponent_color:
                    score += self.w_knight

        # ── 4. 数值覆盖 ──
        enemy_power = sum(t.troop_key if isinstance(t.troop_key, int) else 0
                          for t in node.stack if t.owner == opponent_color)
        my_power = troop.troop_key if isinstance(troop.troop_key, int) else 0
        if my_power > enemy_power:
            score += self.W_BASE_OVERLAP * (my_power - enemy_power)

        # ── 5. 地形要冲 ──
        # 连接数多的节点是战略要冲
        neighbor_count = len(game.board.get_neighbors(node.nid))
        if neighbor_count >= 3:
            score += self.w_terrain

        # ── 6. 地形加成 ──
        terrain = node.terrain_key
        cp = game.current_player
        opp = game.opponent
        if terrain == "city_of_clouds":
            score += 40
        elif terrain == "castle_field":
            score += 30
        elif terrain == "cursed_cemetery" and cp.discard:
            score += 35
        elif terrain == "battlefield" and opp.hand:
            score += 25
        elif terrain == "station_metalx":
            score -= 20

        return score

    def w_hq_capture_if_possible(self, game: GameState, troop: Troop,
                                  node: BoardNode, opponent_color: str) -> int:
        """评估 HQ 夺取可能性。

        如果放置后己方战力超过敌方，返回 HQ 夺取权重。
        """
        my_power = troop.troop_key if isinstance(troop.troop_key, int) else 0
        # 己方已有驻军战力
        my_existing = sum(t.troop_key if isinstance(t.troop_key, int) else 0
                          for t in node.stack if t.owner == self.player_color)
        enemy_power = sum(t.troop_key if isinstance(t.troop_key, int) else 0
                          for t in node.stack if t.owner == opponent_color)

        if (my_power + my_existing) > enemy_power:
            return self.w_hq
        return 0

    def _area_close_bonus(self, game: GameState, node: BoardNode) -> int:
        """评估区域闭合奖励。

        检查放置后是否能完成区域占领（获得星星）。
        """
        if node.area_id is None:
            return 0

        # 统计该区域己方控制的节点数
        area_nodes = [n for n in game.board.nodes.values()
                      if n.area_id == node.area_id]
        if not area_nodes:
            return 0

        my_count = sum(1 for n in area_nodes
                       if n.stack and n.stack[-1].owner == self.player_color)
        total = len(area_nodes)

        # 如果放置后己方控制超过半数，给予区域闭合奖励
        if my_count + 1 >= total // 2 + 1:  # 多数控制
            return self.w_area

        # 接近闭合时给予部分奖励
        ratio = (my_count + 1) / total
        if ratio > 0.5:
            return int(self.w_area * ratio)

        return 0

    def _analyze_areas(self, game: GameState) -> dict:
        """分析所有区域的控制情况。

        Returns:
            字典 {area_id: {"my": count, "enemy": count, "total": count}}
        """
        areas: dict = {}
        for node in game.board.nodes.values():
            aid = node.area_id
            if aid is None:
                continue
            if aid not in areas:
                areas[aid] = {"my": 0, "enemy": 0, "total": 0}
            areas[aid]["total"] += 1
            if node.stack:
                top = node.stack[-1]
                if top.owner == self.player_color:
                    areas[aid]["my"] += 1
                else:
                    areas[aid]["enemy"] += 1
        return areas