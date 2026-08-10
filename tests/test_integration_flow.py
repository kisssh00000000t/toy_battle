"""端到端游戏流程集成测试。"""
import pytest
from ..game.map_loader import load_map
from ..game.board import GameBoard
from ..game.game_logic import GameState
from ..game.troop import Troop


def _make_game():
    """创建并初始化游戏，强制红方先手。"""
    data = load_map()
    board = GameBoard()
    board.load_from_dict(data)
    game = GameState()
    game.board = board
    game.setup()
    game.current_player_color = "red"
    return game


class TestGameFlow:
    """游戏流程端到端测试。"""

    def test_setup_and_initial_state(self):
        game = _make_game()
        assert game.current_player_color == "red"
        assert len(game.red.hand) > 0
        assert len(game.blue.hand) > 0
        assert not game.game_over

    def test_place_troop_on_hq_neighbor(self):
        game = _make_game()
        cp = game.current_player
        hq_nodes = game.board.hq_map.get("red", [])
        assert len(hq_nodes) > 0, "Red should have HQ nodes"

        # 找一个HQ的邻居节点
        neighbors = game.board.get_neighbors(hq_nodes[0])
        assert len(neighbors) > 0, "HQ should have neighbors"

        target_nid = neighbors[0]
        node = game.board.get_node(target_nid)

        # 选一个非飞钩船长、非玩具队长的兵种（队长会触发额外放置不切换回合）
        troop = None
        for t in cp.hand:
            if t.troop_key not in (2, 4):
                troop = t
                break
        assert troop is not None, "Should have non-hook troop"

        ok, err = game.can_place_troop(troop, node)
        assert ok, f"Should be able to place on HQ neighbor: {err}"

        result = game.place_troop(troop, node)
        assert result, "Place should succeed"
        # place_troop 不再自动 end_turn，需手动切换
        game.end_turn()
        assert game.current_player_color == "blue", "Turn should switch to blue"

    def test_draw_cards_action(self):
        game = _make_game()
        cp = game.current_player
        initial_hand = len(cp.hand)
        ok, err = game.draw_cards_action()
        if ok:
            assert game.current_player_color == "blue", "Turn should switch after draw"

    def test_star_check_after_area_control(self):
        """测试星星计分逻辑存在且可调用。"""
        game = _make_game()
        # 直接调用内部方法验证不崩溃
        game._check_star_score()
        assert game.red.star_points >= 0
        assert game.blue.star_points >= 0

    def test_game_not_over_initially(self):
        game = _make_game()
        assert not game.game_over
        assert game.winner is None