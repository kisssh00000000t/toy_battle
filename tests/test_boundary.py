"""
边界条件测试：覆盖粒子系统、回放引擎、棋盘连通性、
游戏逻辑边界条件（星星胜利、额外放置、地形限制等）。
"""

import pytest
from collections import deque

from ..game.board import GameBoard, BoardNode
from ..game.player import Player
from ..game.troop import Troop
from ..game.game_logic import GameState
from ..game.particle import Particle, ParticleSystem
from ..game.replay import ReplayEngine, ReplayState


# ═══════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════

def _make_board_with_areas() -> GameBoard:
    """创建含多个area的棋盘，用于星星胜利测试。"""
    board = GameBoard()
    nodes = [
        # area 0: 红方HQ + 2节点
        {"nid": 0, "x": 100, "y": 100, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
        {"nid": 1, "x": 200, "y": 100, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
        {"nid": 2, "x": 300, "y": 100, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
        # area 1: 中立区 + 2节点
        {"nid": 3, "x": 100, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 1},
        {"nid": 4, "x": 200, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 1},
        # area 2: 蓝方HQ + 2节点
        {"nid": 5, "x": 100, "y": 500, "terrain": "normal", "is_hq": True, "hq_owner": "blue", "area_id": 2},
        {"nid": 6, "x": 200, "y": 500, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 2},
        {"nid": 7, "x": 300, "y": 500, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 2},
    ]
    edges = [
        {"u": 0, "v": 1}, {"u": 1, "v": 2},
        {"u": 0, "v": 3}, {"u": 3, "v": 4},
        {"u": 4, "v": 5}, {"u": 5, "v": 6}, {"u": 6, "v": 7},
    ]
    board.load_from_dict({"nodes": nodes, "edges": edges})
    return board


def _make_game_with_areas() -> GameState:
    """创建含多area的游戏实例。"""
    board = _make_board_with_areas()
    game = GameState()
    game.board = board
    game.setup()
    game.current_player_color = "red"
    return game


def _make_dual_hq_board() -> GameBoard:
    """创建红方双HQ棋盘，测试多源BFS。"""
    board = GameBoard()
    nodes = [
        {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
        {"nid": 1, "x": 200, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
        {"nid": 2, "x": 500, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
        {"nid": 3, "x": 300, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
        {"nid": 4, "x": 400, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
        {"nid": 5, "x": 580, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "blue", "area_id": 0},
    ]
    edges = [
        {"u": 0, "v": 1}, {"u": 1, "v": 3}, {"u": 3, "v": 4}, {"u": 4, "v": 2}, {"u": 2, "v": 5},
    ]
    board.load_from_dict({"nodes": nodes, "edges": edges})
    return board


# ═══════════════════════════════════════════════════════════
#  粒子系统测试
# ═══════════════════════════════════════════════════════════

class TestParticleSystem:
    """粒子系统边界条件测试。"""

    def test_emit_creates_particles(self):
        """emit应创建指定数量的粒子。"""
        ps = ParticleSystem()
        ps.emit(100, 100, count=10)
        assert ps.count == 10

    def test_emit_default_count(self):
        """emit默认count=12。"""
        ps = ParticleSystem()
        ps.emit(0, 0)
        assert ps.count == 12

    def test_update_kills_expired_particles(self):
        """update应回收生命耗尽的粒子。"""
        ps = ParticleSystem()
        ps.emit(0, 0, count=5, life=30)
        assert ps.count == 5
        # 多次update直到所有粒子死亡
        for _ in range(50):
            ps.update()
        assert ps.count == 0

    def test_update_decrements_life(self):
        """update应递减粒子生命。"""
        ps = ParticleSystem()
        ps.emit(0, 0, count=3, life=30)
        # emit 中 life 有 randint(-5,5) 偏移，需多次 update 确保 life < max_life
        for _ in range(10):
            ps.update()
        assert ps.count == 3  # 还活着
        for p in ps.particles:
            assert p.life < p.max_life  # 生命已递减

    def test_clear_removes_all(self):
        """clear应清除所有粒子。"""
        ps = ParticleSystem()
        ps.emit(0, 0, count=20)
        ps.clear()
        assert ps.count == 0

    def test_emit_star_capture(self):
        """emit_star_capture应发射16个金色粒子。"""
        ps = ParticleSystem()
        ps.emit_star_capture(50, 50)
        assert ps.count == 16

    def test_emit_troop_place(self):
        """emit_troop_place应发射8个粒子。"""
        ps = ParticleSystem()
        ps.emit_troop_place(50, 50)
        assert ps.count == 8

    def test_emit_victory(self):
        """emit_victory应发射30个粒子。"""
        ps = ParticleSystem()
        ps.emit_victory(50, 50)
        assert ps.count == 30

    def test_empty_draw_no_crash(self):
        """空粒子系统draw不应崩溃。"""
        ps = ParticleSystem()
        # 使用一个简单的Surface测试draw
        import pygame
        pygame.init()
        surf = pygame.Surface((100, 100))
        ps.draw(surf)  # 不应抛异常

    def test_particle_attributes(self):
        """粒子属性应在合理范围内。"""
        ps = ParticleSystem()
        ps.emit(100, 200, count=1, color=(255, 100, 50))
        p = ps.particles[0]
        assert p.max_life > 0
        assert p.life > 0
        assert len(p.color) == 3
        assert 0 <= p.color[0] <= 255
        assert p.size > 0

    def test_gravity_affects_vy(self):
        """重力应影响vy。"""
        ps = ParticleSystem()
        ps.emit(0, 0, count=1, gravity=0.5)
        p = ps.particles[0]
        old_vy = p.vy
        ps.update()
        # vy应增加（重力向下）
        assert p.vy > old_vy or p.vy != old_vy  # 至少有变化


# ═══════════════════════════════════════════════════════════
#  回放引擎测试
# ═══════════════════════════════════════════════════════════

class TestReplayEngine:
    """回放引擎边界条件测试。"""

    def _make_map_data(self):
        """创建简单地图数据。"""
        return {
            "nodes": [
                {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
                {"nid": 1, "x": 220, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
                {"nid": 2, "x": 340, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "blue", "area_id": 0},
            ],
            "edges": [{"u": 0, "v": 1}, {"u": 1, "v": 2}],
        }

    def test_empty_log(self):
        """空action_log的回放应立即结束。"""
        engine = ReplayEngine(self._make_map_data(), [])
        engine.start()
        result = engine.step()
        assert result is None
        assert engine.state == ReplayState.FINISHED

    def test_step_progress(self):
        """step应推进进度。"""
        log = [{"type": "draw", "player": "red", "data": {"player": "red"}}]
        engine = ReplayEngine(self._make_map_data(), log)
        engine.start()
        assert engine.progress == 0.0
        engine.step()
        assert engine.progress == 1.0

    def test_step_back_at_start(self):
        """在开头step_back应返回None。"""
        log = [{"type": "draw", "player": "red", "data": {"player": "red"}}]
        engine = ReplayEngine(self._make_map_data(), log)
        engine.start()
        engine.step()
        # current_index=0, step_back应返回None
        result = engine.step_back()
        # current_index=0时step_back返回None
        assert result is None

    def test_jump_to_invalid_index(self):
        """跳转到无效索引应返回None。"""
        engine = ReplayEngine(self._make_map_data(), [{"type": "draw", "player": "red", "data": {"player": "red"}}])
        engine.start()
        assert engine.jump_to(-1) is None
        assert engine.jump_to(999) is None

    def test_pause_resume(self):
        """暂停/继续应正确切换状态。"""
        engine = ReplayEngine(self._make_map_data(), [{"type": "draw", "player": "red", "data": {"player": "red"}}])
        engine.start()
        assert engine.state == ReplayState.PLAYING
        engine.pause()
        assert engine.state == ReplayState.PAUSED
        engine.resume()
        assert engine.state == ReplayState.PLAYING

    def test_pause_when_not_playing(self):
        """非PLAYING状态pause不应改变状态。"""
        engine = ReplayEngine(self._make_map_data(), [])
        engine.start()
        engine.step()  # FINISHED
        engine.pause()
        assert engine.state == ReplayState.FINISHED

    def test_total_actions(self):
        """total_actions应返回日志长度。"""
        log = [{"type": "draw", "player": "red", "data": {"player": "red"}}] * 5
        engine = ReplayEngine(self._make_map_data(), log)
        assert engine.total_actions == 5

    def test_get_snapshot_before_start(self):
        """start前get_snapshot应返回None。"""
        engine = ReplayEngine(self._make_map_data(), [])
        assert engine.get_snapshot() is None

    def test_on_step_callback(self):
        """on_step回调应在每次step后调用。"""
        log = [{"type": "draw", "player": "red", "data": {"player": "red"}}]
        engine = ReplayEngine(self._make_map_data(), log)
        called = []
        engine.on_step(lambda a: called.append(a))
        engine.start()
        engine.step()
        assert len(called) == 1

    def test_ready_state_before_start(self):
        """start前应为READY状态。"""
        engine = ReplayEngine(self._make_map_data(), [])
        assert engine.state == ReplayState.READY

    def test_auto_start_on_step(self):
        """未start时step应自动start。"""
        log = [{"type": "draw", "player": "red", "data": {"player": "red"}}]
        engine = ReplayEngine(self._make_map_data(), log)
        # 不调用start，直接step
        result = engine.step()
        assert result is not None
        assert engine.state == ReplayState.PLAYING


# ═══════════════════════════════════════════════════════════
#  棋盘连通性边界测试
# ═══════════════════════════════════════════════════════════

class TestBoardConnectivity:
    """棋盘连通性边界条件测试。"""

    def test_multi_hq_bfs(self):
        """多HQ的BFS应从所有HQ同时搜索。"""
        board = _make_dual_hq_board()
        # 节点0和节点2都是红方HQ
        # 无兵种时，只有HQ在visited中
        # 节点1与HQ0相邻，应该连通（相邻判断）
        assert board.is_connected_to_hq(1, "red") is True
        # 节点3不与任何HQ直接相邻，无兵种时不连通
        assert board.is_connected_to_hq(3, "red") is False
        # 在中间节点放置红方兵种后，节点3应连通
        node1 = board.get_node(1)
        node1.stack.append(Troop(1, "red"))
        node4 = board.get_node(4)
        node4.stack.append(Troop(1, "red"))
        assert board.is_connected_to_hq(3, "red") is True

    def test_disconnected_node(self):
        """不连通节点应返回False。"""
        board = GameBoard()
        nodes = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 500, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 1},
        ]
        board.load_from_dict({"nodes": nodes, "edges": []})
        assert board.is_connected_to_hq(1, "red") is False

    def test_hq_self_is_connected(self):
        """HQ自身应连通。"""
        board = GameBoard()
        nodes = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
        ]
        board.load_from_dict({"nodes": nodes, "edges": []})
        assert board.is_connected_to_hq(0, "red") is True

    def test_no_hq_for_owner(self):
        """无HQ的玩家应全部不连通。"""
        board = GameBoard()
        nodes = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 200, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
        ]
        edges = [{"u": 0, "v": 1}]
        board.load_from_dict({"nodes": nodes, "edges": edges})
        assert board.is_connected_to_hq(0, "blue") is False
        assert board.is_connected_to_hq(1, "blue") is False

    def test_star_points_loading(self):
        """star_points应正确加载。"""
        board = GameBoard()
        data = {
            "nodes": [
                {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            ],
            "edges": [],
            "star_points": [{"x": 150, "y": 300, "area_id": 0, "has_star": True}],
        }
        board.load_from_dict(data)
        assert len(board.star_points) == 1
        assert board.star_points[0]["has_star"] is True

    def test_empty_star_points(self):
        """无star_points数据应默认空列表。"""
        board = GameBoard()
        data = {
            "nodes": [
                {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            ],
            "edges": [],
        }
        board.load_from_dict(data)
        assert board.star_points == []


# ═══════════════════════════════════════════════════════════
#  游戏逻辑边界条件测试
# ═══════════════════════════════════════════════════════════

class TestGameLogicBoundary:
    """游戏逻辑边界条件测试。"""

    def test_place_after_game_over_fails(self):
        """游戏结束后放置应失败。"""
        game = _make_game_with_areas()
        game.game_over = True
        game.winner = "red"
        cp = game.current_player
        troop = cp.hand[0] if cp.hand else Troop(7, cp.color)
        node = game.board.get_node(1)
        ok, err = game.can_place_troop(troop, node)
        assert ok is False
        assert "结束" in err

    def test_draw_after_game_over_fails(self):
        """游戏结束后抽卡应失败。"""
        game = _make_game_with_areas()
        game.game_over = True
        ok, err = game.draw_cards_action()
        assert ok is False

    def test_toy_captain_extra_place(self):
        """玩具队长(key=2)应触发额外放置。"""
        game = _make_game_with_areas()
        cp = game.current_player
        captain = Troop(2, cp.color)
        cp.hand.append(captain)
        node = game.board.get_node(1)
        result = game.place_troop(captain, node)
        assert result is True
        assert game.extra_place_pending is True

    def test_tropical_pool_even_only(self):
        """热带泳池应拒绝奇数兵种。"""
        board = GameBoard()
        nodes = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 220, "y": 300, "terrain": "tropical_pool", "is_hq": False, "hq_owner": None, "area_id": 0},
        ]
        edges = [{"u": 0, "v": 1}]
        board.load_from_dict({"nodes": nodes, "edges": edges})
        game = GameState()
        game.board = board
        game.setup()
        game.current_player_color = "red"
        cp = game.current_player
        # 奇数兵种
        odd_troop = Troop(3, cp.color)
        cp.hand.append(odd_troop)
        node = game.board.get_node(1)
        ok, err = game.can_place_troop(odd_troop, node)
        assert ok is False
        assert "偶数" in err
        # 偶数兵种
        even_troop = Troop(4, cp.color)
        cp.hand.append(even_troop)
        ok2, _ = game.can_place_troop(even_troop, node)
        assert ok2 is True

    def test_hook_captain_skips_connectivity(self):
        """飞钩船长(key=4)应跳过连通性检查。"""
        board = GameBoard()
        nodes = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 500, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 1},
        ]
        board.load_from_dict({"nodes": nodes, "edges": []})
        game = GameState()
        game.board = board
        game.setup()
        game.current_player_color = "red"
        cp = game.current_player
        hook = Troop(4, cp.color)
        cp.hand.append(hook)
        node = game.board.get_node(1)
        # 节点1不连通，但飞钩船长应跳过连通检查
        ok, _ = game.can_place_troop(hook, node)
        assert ok is True

    def test_hook_captain_blocked_from_enemy_hq(self):
        """飞钩船长不能直接投放敌方HQ。"""
        board = GameBoard()
        nodes = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 300, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "blue", "area_id": 0},
        ]
        edges = [{"u": 0, "v": 1}]
        board.load_from_dict({"nodes": nodes, "edges": edges})
        game = GameState()
        game.board = board
        game.setup()
        game.current_player_color = "red"
        cp = game.current_player
        hook = Troop(4, cp.color)
        cp.hand.append(hook)
        enemy_hq = game.board.get_node(1)
        ok, err = game.can_place_troop(hook, enemy_hq)
        assert ok is False
        assert "敌方基地" in err

    def test_star_score_area_capture(self):
        """完全占领区块应获得星星。"""
        game = _make_game_with_areas()
        cp = game.current_player
        # 占领area 0的所有节点(0,1,2)
        for nid in [1, 2]:
            node = game.board.get_node(nid)
            t = Troop(7, cp.color)
            node.stack.append(t)
        # area 0: 节点0是HQ(红方), 节点1和2都有红方兵种
        result = game._check_star_score()
        assert result is False  # 还没达到star_win_goal
        assert cp.star_points >= 1  # 至少获得1颗星星
        assert 0 in cp.captured_areas

    def test_star_score_no_duplicate(self):
        """同一区块不应重复获得星星。"""
        game = _make_game_with_areas()
        cp = game.current_player
        for nid in [1, 2]:
            node = game.board.get_node(nid)
            t = Troop(7, cp.color)
            node.stack.append(t)
        game._check_star_score()
        stars1 = cp.star_points
        game._check_star_score()
        stars2 = cp.star_points
        assert stars1 == stars2  # 不应重复加星

    def test_end_turn_resets_counters(self):
        """end_turn应重置放置计数和额外放置标记。"""
        game = _make_game_with_areas()
        game.turn_place_count = 1
        game.extra_place_pending = True
        game.end_turn()
        assert game.turn_place_count == 0
        assert game.extra_place_pending is False

    def test_end_turn_when_game_over(self):
        """游戏结束后end_turn不应切换玩家。"""
        game = _make_game_with_areas()
        game.game_over = True
        old_color = game.current_player_color
        game.end_turn()
        assert game.current_player_color == old_color

    def test_joker_overwrite_enemy(self):
        """Joker应能覆盖敌方任何兵种。"""
        board = GameBoard()
        nodes = [
            {"nid": 0, "x": 100, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 220, "y": 300, "terrain": "normal", "is_hq": False, "hq_owner": None, "area_id": 0},
            {"nid": 2, "x": 340, "y": 300, "terrain": "normal", "is_hq": True, "hq_owner": "blue", "area_id": 0},
        ]
        edges = [{"u": 0, "v": 1}, {"u": 1, "v": 2}]
        board.load_from_dict({"nodes": nodes, "edges": edges})
        game = GameState()
        game.board = board
        game.setup()
        game.current_player_color = "red"
        cp = game.current_player
        # 红方放一个兵到节点1
        t1 = cp.hand[0]
        game.place_troop(t1, game.board.get_node(1))
        game.end_turn()
        # 蓝方放一个强兵到节点1
        blue = game.current_player
        strong = Troop(7, "blue")
        blue.hand.append(strong)
        game.place_troop(strong, game.board.get_node(1))
        game.end_turn()
        # 红方用Joker覆盖
        cp = game.current_player
        joker = Troop("joker", cp.color)
        cp.hand.append(joker)
        ok, _ = game.can_place_troop(joker, game.board.get_node(1))
        assert ok is True


# ═══════════════════════════════════════════════════════════
#  Player 边界条件测试
# ═══════════════════════════════════════════════════════════

class TestPlayerBoundary:
    """Player边界条件测试。"""

    def test_draw_from_empty_reserve(self):
        """空备用堆抽牌应返回0。"""
        p = Player("red")
        p.reserve = []
        got = p.draw(3)
        assert got == 0
        assert len(p.hand) == 0

    def test_draw_respects_hand_limit(self):
        """抽牌应受手牌上限限制。"""
        from ..game.constants import HAND_MAX
        p = Player("red")
        # 使用有效key生成备用堆
        valid_keys = [1, 2, 3, 4, 5, 6, 7, "joker"]
        p.reserve = [Troop(valid_keys[i % len(valid_keys)], "red") for i in range(20)]
        # 填满手牌
        while len(p.hand) < HAND_MAX:
            p.hand.append(p.reserve.pop())
        got = p.draw(2)
        assert got == 0

    def test_return_to_hand_when_full(self):
        """手牌满时return_to_hand应失败。"""
        from ..game.constants import HAND_MAX
        p = Player("red")
        valid_keys = [1, 2, 3, 4, 5, 6, 7, "joker"]
        p.hand = [Troop(valid_keys[i % len(valid_keys)], "red") for i in range(HAND_MAX)]
        t = Troop(7, "red")
        p.discard.append(t)
        result = p.return_to_hand(t)
        assert result is False

    def test_seal_and_unseal(self):
        """封存和归还手牌流程。"""
        p = Player("red")
        t = Troop(5, "red")
        p.hand.append(t)
        p.seal_troop(t)
        assert t not in p.hand
        assert p.sealed_troop is t
        p.unseal_troop()
        assert t in p.hand
        assert p.sealed_troop is None

    def test_unseal_when_hand_full(self):
        """手牌满时unseal应进入弃牌堆。"""
        from ..game.constants import HAND_MAX
        p = Player("red")
        valid_keys = [1, 2, 3, 4, 5, 6, 7, "joker"]
        p.hand = [Troop(valid_keys[i % len(valid_keys)], "red") for i in range(HAND_MAX)]
        t = Troop(7, "red")
        p.sealed_troop = t
        p.unseal_troop()
        assert t in p.discard
        assert p.sealed_troop is None

    def test_can_draw(self):
        """can_draw应正确判断。"""
        p = Player("red")
        p.reserve = []
        p.hand = []
        assert p.can_draw() is False  # 空备用堆
        p.reserve = [Troop(1, "red")]
        assert p.can_draw() is True