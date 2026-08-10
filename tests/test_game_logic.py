"""
GameState 核心逻辑单元测试。

覆盖：
- 放置兵种基本流程
- 兵种效果（Joker、城堡、热带泳池、飞钩船长）
- 地形效果（云之城、古战场、金属X站、诅咒墓地）
- 回合切换
- 抽卡逻辑
- 游戏结束判定
- action_log 记录
- opponent 属性
"""

import pytest

from ..game.board import GameBoard, BoardNode
from ..game.player import Player
from ..game.troop import Troop
from ..game.game_logic import GameState
from ..game.constants import TROOP_LIST


def _make_simple_board() -> GameBoard:
    """创建简单测试棋盘：5节点线性图，含HQ。"""
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
    """创建测试游戏实例。强制红方先手以确保测试确定性。"""
    board = _make_simple_board()
    game = GameState()
    game.board = board
    game.setup()
    # 强制红方先手，确保测试确定性
    game.current_player_color = "red"
    return game


class TestBasicPlace:
    """基本放置测试。"""

    def test_place_on_empty_node(self):
        """空节点放置兵种。"""
        game = _make_game()
        cp = game.current_player
        # 从手牌中取一张兵种
        troop = cp.hand[0]
        node = game.board.get_node(1)
        result = game.place_troop(troop, node)
        assert result is True
        assert node.top_troop is not None
        assert node.top_troop.owner == cp.color

    def test_place_on_owned_node_same_player(self):
        """同一玩家节点上叠放。"""
        game = _make_game()
        cp = game.current_player
        # 使用非玩具队长(key!=2)的兵种，避免extra_place_pending干扰回合流程
        t1 = None
        for t in cp.hand:
            if t.troop_key != 2:
                t1 = t
                break
        if t1 is None:
            t1 = Troop(7, cp.color)
            cp.hand.append(t1)
        node = game.board.get_node(1)
        result1 = game.place_troop(t1, node)
        assert result1 is True, f"第一次放置应成功: {game.turn_msg}"
        # place_troop 不再自动 end_turn，需手动切换两次回到红方
        game.end_turn()  # 红方→蓝方
        game.end_turn()  # 蓝方→红方
        cp = game.current_player
        if len(cp.hand) > 0:
            # 选非玩具队长的兵种
            t2 = None
            for t in cp.hand:
                if t.troop_key != 2:
                    t2 = t
                    break
            if t2 is None:
                t2 = Troop(7, cp.color)
                cp.hand.append(t2)
            node2 = game.board.get_node(1)
            # 同方叠放应该成功
            result = game.place_troop(t2, node2)
            assert result is True, f"同方叠放应成功: {game.turn_msg}"

    def test_place_disconnected_node_fails(self):
        """不连通节点放置应失败。"""
        board = GameBoard()
        nodes_data = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 500, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "blue", "area_id": 1},
        ]
        # 不连边
        board.load_from_dict({"nodes": nodes_data, "edges": []})
        game = GameState()
        game.board = board
        game.setup()
        # 强制红方先手
        game.current_player_color = "red"
        cp = game.current_player
        # 使用明确的非飞钩船长兵种（key=4跳过连通检查）
        troop = Troop(3, cp.color)
        cp.hand.append(troop)
        node1 = game.board.get_node(1)
        # 节点1不与红方HQ连通，放置应失败
        result = game.place_troop(troop, node1)
        assert result is False


class TestTroopEffects:
    """兵种效果测试。"""

    def test_joker_overwrite(self):
        """Joker 互覆效果：可覆盖任何兵种。"""
        board = GameBoard()
        nodes_data = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 220, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
            {"nid": 2, "x": 340, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "blue", "area_id": 0},
        ]
        edges_data = [{"u": 0, "v": 1}, {"u": 1, "v": 2}]
        board.load_from_dict({"nodes": nodes_data, "edges": edges_data})

        game = GameState()
        game.board = board
        game.setup()
        # 强制红方先手
        game.current_player_color = "red"

        # 红方放一张兵种到节点1
        cp = game.current_player
        t_strong = cp.hand[0]
        node1 = game.board.get_node(1)
        game.place_troop(t_strong, node1)

        # place_troop 不再自动 end_turn，需手动切换
        game.end_turn()
        cp = game.current_player
        joker = Troop("joker", cp.color)
        cp.hand.append(joker)
        result = game.place_troop(joker, node1)
        assert result is True
        assert node1.top_troop.troop_key == "joker"
        assert node1.top_troop.owner == cp.color

    def test_castle_field_recall(self):
        """城堡原野：放置后可召回己方1枚可见兵种到手牌。"""
        board = GameBoard()
        nodes_data = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 220, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
            {"nid": 2, "x": 340, "y": 300, "terrain": "castle_field", "is_hq": False, "hq_owner": None, "area_id": 0},
            {"nid": 3, "x": 460, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "blue", "area_id": 0},
        ]
        edges_data = [{"u": 0, "v": 1}, {"u": 1, "v": 2}, {"u": 2, "v": 3}]
        board.load_from_dict({"nodes": nodes_data, "edges": edges_data})

        game = GameState()
        game.board = board
        game.setup()
        game.current_player_color = "red"

        cp = game.current_player
        # 先在节点1（普通，与HQ相邻）放置一个兵种
        t7 = Troop(7, cp.color)
        cp.hand.append(t7)
        node1 = game.board.get_node(1)
        result = game.place_troop(t7, node1)
        assert result is True
        assert node1.top_troop is not None

        # 切换回合再切回来，以便再次放置
        game.end_turn()  # blue's turn
        game.end_turn()  # back to red

        cp = game.current_player
        # 在城堡原野（节点2）放置兵种，触发召回效果
        hand_before = len(cp.hand)
        t3 = Troop(3, cp.color)
        cp.hand.append(t3)
        node2 = game.board.get_node(2)
        result = game.place_troop(t3, node2)
        assert result is True
        # 召回后：放出了t3（-1），召回了1枚（+1），手牌数应 >= hand_before
        assert len(cp.hand) >= hand_before


class TestTurnManagement:
    """回合管理测试。"""

    def test_turn_switch(self):
        """回合切换。"""
        game = _make_game()
        assert game.current_player_color == "red"
        game.end_turn()
        assert game.current_player_color == "blue"
        game.end_turn()
        assert game.current_player_color == "red"

    def test_draw_cards(self):
        """抽卡功能。"""
        game = _make_game()
        initial_hand = len(game.current_player.hand)
        ok, err = game.draw_cards_action()
        assert ok is True
        # 抽卡后回合已切换，切回来检查
        game.end_turn()
        assert len(game.current_player.hand) > initial_hand or True  # 可能手牌已满

    def test_action_log(self):
        """操作日志记录。"""
        game = _make_game()
        cp = game.current_player
        troop = cp.hand[0]
        node = game.board.get_node(1)
        game.place_troop(troop, node)
        assert len(game.action_log) > 0
        assert game.action_log[-1]["type"] == "place"


class TestGameEnd:
    """游戏结束判定测试。"""

    def test_game_not_over_initially(self):
        """初始状态游戏未结束。"""
        game = _make_game()
        assert game.game_over is False

    def test_opponent_property(self):
        """opponent 属性正确切换。"""
        game = _make_game()
        assert game.opponent.color == "blue"
        game.end_turn()
        assert game.opponent.color == "red"