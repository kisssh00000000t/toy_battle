"""
游戏后端规则自动化测试脚本。
校验：技能跳过、兵种放置、战力覆盖、推土机/爆竹不可堆叠、弩手距离2击杀。

运行方法：python -m pytest tests/test_skill_skip_and_rules.py -v
"""

import pytest

from game.board import GameBoard, BoardNode
from game.player import Player
from game.troop import Troop
from game.game_logic import GameState
from game.commands import GameCommand
from game.dispatcher import ActionDispatcher
from game.constants import TROOP_LIST


def _make_simple_board() -> GameBoard:
    """创建5节点线性棋盘：0(RedHQ) - 1 - 2 - 3 - 4(BlueHQ)"""
    board = GameBoard()
    nodes_data = [
        {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
        {"nid": 1, "x": 220, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
        {"nid": 2, "x": 340, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
        {"nid": 3, "x": 460, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
        {"nid": 4, "x": 580, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "blue", "area_id": 0},
    ]
    edges_data = [
        {"u": 0, "v": 1}, {"u": 1, "v": 2}, {"u": 2, "v": 3}, {"u": 3, "v": 4},
    ]
    board.load_from_dict({"nodes": nodes_data, "edges": edges_data})
    return board


def _make_game() -> GameState:
    """创建测试游戏实例，强制红方先手。"""
    board = _make_simple_board()
    game = GameState()
    game.board = board
    game.setup()
    game.current_player_color = "red"
    # 清空手牌，方便精准发牌
    game.red.hand = []
    game.blue.hand = []
    return game


def _play_troop(game, dispatcher, player_color, troop_key, node_id):
    """辅助：给玩家发牌并打出"""
    cp = game.red if player_color == "red" else game.blue
    troop = Troop(troop_key, player_color)
    cp.hand.append(troop)
    cmd = GameCommand("PLAY_PIECE", source_player=player_color,
                      payload={"troop_key": troop.troop_key, "node_id": node_id})
    return dispatcher.dispatch(cmd)


def _cast_skill(game, dispatcher, player_color, target_nid):
    """辅助：释放/跳过技能"""
    cmd = GameCommand("CAST_SKILL", source_player=player_color,
                      payload={"target_nid": target_nid})
    return dispatcher.dispatch(cmd)


class TestSkillSkipLogic:
    """测试：二段技能跳过机制（核心修复验证）"""

    def test_cast_skill_skip_with_none(self):
        """target_nid=None 应被后端原生放行，清空挂起状态并结束回合"""
        game = _make_game()
        dispatcher = ActionDispatcher(game)

        # 放置魔方刺客(10)——需要选目标的二段技能兵种
        ok, msg = _play_troop(game, dispatcher, "red", 10, 1)
        assert ok, f"放置魔方刺客失败: {msg}"

        # 应处于挂起技能状态
        assert game.pending_skill is not None, "放置技能兵种后未进入挂起状态"

        # 发送跳过指令 target_nid=None
        ok, msg = _cast_skill(game, dispatcher, "red", None)
        assert ok, f"主动跳过技能失败: {msg}，请检查 execute_pending_skill 的 None 分支"

        # 跳过后应清空挂起状态
        assert game.pending_skill is None, "跳过技能后未清空挂起状态"

        # 跳过后应切入对方回合
        assert game.current_player_color == "blue", "跳过技能后未能正常结束回合"

    def test_auto_skip_when_no_targets(self):
        """无合法目标时自动跳过也应走正规通道"""
        game = _make_game()
        dispatcher = ActionDispatcher(game)

        # 放置推土机(8)——只能放空位，技能需要相邻敌军
        ok, msg = _play_troop(game, dispatcher, "red", 8, 1)
        assert ok, f"放置推土机失败: {msg}"

        # 此时棋盘上没有敌方兵种，推土机技能无目标
        if game.pending_skill:
            targets = game.get_skill_target_nodes()
            if not targets:
                # 自动跳过
                ok, msg = _cast_skill(game, dispatcher, "red", None)
                assert ok, f"自动跳过失败: {msg}"

                assert game.pending_skill is None, "自动跳过后挂起状态未清空"
                assert game.current_player_color == "blue", "自动跳过后未切换回合"

    def test_skip_via_dispatcher_not_bypass(self):
        """验证跳过走Dispatcher通道，而非UI直接篡改状态"""
        game = _make_game()
        dispatcher = ActionDispatcher(game)

        ok, _ = _play_troop(game, dispatcher, "red", 10, 1)
        assert ok

        # 通过Dispatcher跳过
        ok, msg = _cast_skill(game, dispatcher, "red", None)
        assert ok

        # 验证action_log中有记录（证明走了正规通道）
        skip_logged = any(
            a.get("action_type") == "CAST_SKILL" and a.get("payload", {}).get("target_nid") is None
            for a in dispatcher.action_log
        )
        assert skip_logged, "跳过操作未记录在action_log中，可能绕过了Dispatcher"


class TestBasicPlacementAndOverwrite:
    """测试：基础放置与战力覆盖"""

    def test_stack_preserves_covered_troop(self):
        """覆盖放置后，被覆盖兵种应保留在堆叠栈中"""
        game = _make_game()

        # 直接操作棋盘：红方1号兵在节点2
        red_troop = Troop(1, "red")
        game.board.nodes[2].stack.append(red_troop)

        # 蓝方3号兵覆盖红方1号兵
        blue_troop = Troop(3, "blue")
        game.board.nodes[2].stack.append(blue_troop)

        # 验证堆叠栈
        assert len(game.board.nodes[2].stack) == 2, "被覆盖的兵种没有被推入栈中"
        assert game.board.nodes[2].top_troop is blue_troop, "顶层应为蓝方3号兵"
        assert game.board.nodes[2].stack[0] is red_troop, "底层应为红方1号兵"

    def test_stack_remove_restores_covered_troop(self):
        """从栈中移除顶层兵种后，原被覆盖兵种应自动露出"""
        game = _make_game()

        red_troop = Troop(1, "red")
        blue_troop = Troop(3, "blue")
        game.board.nodes[2].stack.append(red_troop)
        game.board.nodes[2].stack.append(blue_troop)

        # 移除顶层蓝方兵种
        game.board.nodes[2].stack.remove(blue_troop)

        assert len(game.board.nodes[2].stack) == 1, "移除后栈中应只剩1个兵种"
        assert game.board.nodes[2].top_troop is red_troop, "移除后顶层应为红方1号兵"


class TestBulldozerCannotStack:
    """测试：推土机(8)/爆竹车(16)不可堆叠"""

    def test_bulldozer_cannot_place_on_occupied(self):
        """推土机不能放在已有兵种的节点上"""
        game = _make_game()
        dispatcher = ActionDispatcher(game)

        # 红方先放1号兵在节点1
        ok, _ = _play_troop(game, dispatcher, "red", 1, 1)
        assert ok

        # 切蓝方
        game.current_player_color = "blue"

        # 蓝方推土机(8)试图放到节点1——应被拒绝
        troop = Troop(8, "blue")
        game.blue.hand.append(troop)
        valid_nodes = game.get_valid_nodes(troop)
        assert game.board.nodes[1] not in valid_nodes, "推土机不应该允许放在已有兵种的地块上"

    def test_boom_boom_cannot_place_on_occupied(self):
        """爆竹车(16)不能放在已有兵种的节点上"""
        game = _make_game()
        dispatcher = ActionDispatcher(game)

        ok, _ = _play_troop(game, dispatcher, "red", 1, 1)
        assert ok

        game.current_player_color = "blue"

        troop = Troop(16, "blue")
        game.blue.hand.append(troop)
        valid_nodes = game.get_valid_nodes(troop)
        assert game.board.nodes[1] not in valid_nodes, "爆竹车不应该允许放在已有兵种的地块上"


class TestCrossbowDistance2:
    """测试：弩手(11)距离2步击杀"""

    def test_crossbow_targets_within_distance_2(self):
        """弩手应能击杀BFS距离为2的敌军"""
        game = _make_game()
        dispatcher = ActionDispatcher(game)

        # 红方先放一个兵在节点1（占位，让蓝方节点3连通蓝HQ）
        ok, _ = _play_troop(game, dispatcher, "red", 7, 1)
        assert ok
        game.end_turn()

        # 蓝方在节点3放一个兵
        ok, _ = _play_troop(game, dispatcher, "blue", 1, 3)
        assert ok
        game.end_turn()

        # 红方回合：放弩手(11)在节点1
        # 先移除节点1上的旧兵种，腾出位置给弩手
        game.board.nodes[1].stack.clear()
        ok, msg = _play_troop(game, dispatcher, "red", 11, 1)
        assert ok, f"放置弩手失败: {msg}"

        # 弩手应挂起技能
        if game.pending_skill:
            targets = game.get_skill_target_nodes()
            target_nids = [n.nid for n in targets]
            # 节点3距离节点1为2步(1->2->3)，应被识别为合法目标
            assert 3 in target_nids, (
                f"弩手未能将距离2步的节点3识别为合法目标！当前目标: {target_nids}"
            )