"""
行动分发控制器（Action Dispatcher）。

统一操作分发管道：确保单机、AI、网战、回放全部同源驱动。

核心职责：
    1. 序列号自增与校对（杜绝跳帧执行）
    2. 核心路由执行（DRAW_CARD / PLAY_PIECE / END_TURN / SELECT_TARGET / SYNC_INIT）
    3. 归档 action_log（JSON 友好字典）
    4. 驱动 UI 表现钩子（on_action_executed 回调）

数据流架构：
    [人类点击/拖拽] [AI决策] [Socket接收远端JSON]
              │           │           │
              └──────►────┴────►──────┘
                         ▼
           【统一入口：ActionDispatcher】
      1. 校验 seq_id 与回合权限
      2. 注入/同步 RNG 随机数种子
      3. 驱动 GameState 纯逻辑执行
      4. 将成功执行的 Command 记入 action_log
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
【本地 UI 表现响应】              【网络模式转发 (可选)】
- 播放放置/吃子/抽卡音效          - 将 Command JSON 发给远端
- 触发目标节点粒子特效            - 广播 State Hash 校验码
- 刷新棋盘/手牌缓存
"""

import logging
from typing import Optional, Callable

from .commands import GameCommand
from .game_logic import GameState

logger = logging.getLogger(__name__)


class ActionDispatcher:
    """统一操作分发管道：确保单机、AI、网战、回放全部同源驱动。

    Attributes:
        game: GameState 实例
        current_seq_id: 当前序列号
        action_log: 已执行的命令流水（JSON 友好字典列表）
        on_action_executed: UI 表现层钩子（逻辑执行成功后通知 UI）
    """

    def __init__(self, game_state: GameState):
        self.game = game_state
        self.current_seq_id = 0
        self.action_log: list[dict] = []

        # UI 表现层钩子 (逻辑执行成功后，通知 UI 播放动画/声音)
        # 签名: (cmd: GameCommand, ok: bool, msg: str) -> None
        self.on_action_executed: Optional[Callable[[GameCommand, bool, str], None]] = None

    def reset(self):
        """重置状态与序列号。"""
        self.current_seq_id = 0
        self.action_log.clear()

    def dispatch(self, cmd: GameCommand, is_remote: bool = False) -> tuple[bool, str]:
        """执行标准化命令，返回 (是否成功, 错误信息)。

        Args:
            cmd: 待执行的指令
            is_remote: True 表示来自网络远端或回放，
                       序列号跳过严格等值自增，直接向对端看齐

        Returns:
            (是否成功, 消息字符串)
        """
        # ── 1. 序列号校对与自增赋值 ──
        if not is_remote and cmd.seq_id == -1:
            cmd.seq_id = self.current_seq_id
        elif is_remote:
            # 网战接收或战报回放时，以指令中自带的 seq_id 为准
            self.current_seq_id = max(self.current_seq_id, cmd.seq_id)

        # ── 2. 核心路由执行 ──
        ok, msg = False, "未知操作类型"

        if cmd.action_type == "DRAW_CARD":
            ok, msg = self._handle_draw(cmd)
        elif cmd.action_type == "PLAY_PIECE":
            ok, msg = self._handle_place(cmd)
        elif cmd.action_type == "END_TURN":
            ok, msg = self._handle_end_turn(cmd)
        elif cmd.action_type == "CAST_SKILL":
            ok, msg = self._handle_cast_skill(cmd)
        elif cmd.action_type == "SELECT_TARGET":
            ok, msg = self._handle_select_target(cmd)
        elif cmd.action_type == "SYNC_INIT":
            ok, msg = self._handle_sync_init(cmd)
        else:
            logger.warning(f"未知指令类型: {cmd.action_type}")
            msg = f"未知指令类型: {cmd.action_type}"

        # ── 3. 归档与序列推进 ──
        if ok:
            self.current_seq_id += 1
            # 严格存入 JSON 友好字典
            self.action_log.append(cmd.to_dict())
            logger.debug(f"[Seq {cmd.seq_id}] Action [{cmd.action_type}] 成功: {msg}")
        else:
            logger.warning(f"[Seq {cmd.seq_id}] Action [{cmd.action_type}] 被驳回: {msg}")

        # ── 4. 驱动 UI 钩子 ──
        if self.on_action_executed:
            self.on_action_executed(cmd, ok, msg)

        return ok, msg

    # ─── 内部命令处理逻辑 ──────────────────────────────────

    def _handle_draw(self, cmd: GameCommand) -> tuple[bool, str]:
        """处理抽卡指令。"""
        if self.game.game_over:
            return False, "游戏已结束"
        if cmd.source_player != self.game.current_player_color:
            return False, "非当前玩家行动回合"

        ok, err = self.game.draw_cards_action()
        return (True, self.game.turn_msg) if ok else (False, err)

    def _handle_place(self, cmd: GameCommand) -> tuple[bool, str]:
        """处理放置兵种指令。"""
        if self.game.game_over:
            return False, "游戏已结束"
        if cmd.source_player != self.game.current_player_color:
            return False, "非当前玩家行动回合"

        t_key = cmd.payload.get("troop_key")
        node_id = cmd.payload.get("node_id")

        # 从手牌寻卡（确定性识别：字符串与 ID 双重容错）
        cp = self.game.current_player
        troop = next(
            (t for t in cp.hand if str(t.troop_key) == str(t_key)), None
        )
        node = self.game.board.get_node(int(node_id)) if node_id is not None else None

        if not troop or not node:
            return False, "未能在手牌或地图中找到指定单位/节点"

        ok = self.game.place_troop(troop, node)
        return (True, self.game.turn_msg) if ok else (False, self.game.turn_msg)

    def _handle_end_turn(self, cmd: GameCommand) -> tuple[bool, str]:
        """处理回合切换指令。"""
        if self.game.game_over:
            return False, "游戏已结束"
        if cmd.source_player != self.game.current_player_color:
            return False, "非当前玩家行动回合"

        self.game.end_turn()
        return True, "回合已切换"

    def _handle_cast_skill(self, cmd: GameCommand) -> tuple[bool, str]:
        """处理二段指向性技能指令（推土/磁铁/魔方/弩手）。

        由 UI 层在玩家点击目标节点后组装 CAST_SKILL 指令，
        经此管道统一驱动 GameState.execute_pending_skill 结算。

        payload 必须包含:
            target_nid: int — 玩家选择的目标节点ID
        """
        if self.game.game_over:
            return False, "游戏已结束"
        if cmd.source_player != self.game.current_player_color:
            return False, "非当前玩家行动回合"
        if not self.game.pending_skill:
            return False, "当前无挂起的技能"

        target_nid = cmd.payload.get("target_nid")
        # target_nid 为 None 表示主动跳过技能（后端原生支持）
        if target_nid is not None:
            target_nid = int(target_nid)

        ok, msg = self.game.execute_pending_skill(target_nid)
        return (ok, msg) if ok else (False, msg)

    def _handle_select_target(self, cmd: GameCommand) -> tuple[bool, str]:
        """处理玩家选择目标指令（回收/召回/封印/回旋等 pending_selection 场景）。

        payload 必须包含:
            target_nid: int — 玩家选择的目标节点ID
            selection_type: str — 选择类型（如 "recall", "seal", "boomerang" 等）
        """
        if self.game.game_over:
            return False, "游戏已结束"
        if cmd.source_player != self.game.current_player_color:
            return False, "非当前玩家行动回合"
        if not self.game.pending_selection:
            return False, "当前无挂起的选择"

        target_nid = cmd.payload.get("target_nid")
        if target_nid is not None:
            target_nid = int(target_nid)

        ok, msg = self.game.resolve_selection(target_nid)
        return (ok, msg) if ok else (False, msg)

    def _handle_sync_init(self, cmd: GameCommand) -> tuple[bool, str]:
        """处理全量快照同步指令（用于网络重连/超时救急）。"""
        try:
            map_data = cmd.payload.get("map_data")
            game_state_data = cmd.payload.get("game_state")
            if map_data:
                self.game.board.load_from_dict(map_data)
            if game_state_data:
                self.game.from_dict(game_state_data)
            return True, "快照覆盖成功"
        except Exception as e:
            return False, f"快照恢复失败: {e}"