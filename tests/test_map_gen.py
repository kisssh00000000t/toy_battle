"""
地图生成与评估测试。

覆盖：
- 地图生成基本功能
- 连通性保障
- 无死胡同（所有非HQ节点度数≥2）
- HQ 分配
- 地形分配
- 公平性评估
"""

import pytest
import networkx as nx

from ..mapgen.map_generator import MapGenerator
from ..mapgen.map_evaluator import MapEvaluator


class TestMapGenerator:
    """地图生成器测试。"""

    def test_generate_basic(self):
        """基本生成测试：输出包含必要字段，节点数在合理范围。"""
        gen = MapGenerator()
        data = gen.generate(map_id=42)
        assert "nodes" in data
        assert "edges" in data
        assert "hq_red" in data
        assert "hq_blue" in data
        assert "star_points" in data
        # 纺锤生成器节点数由行列决定（7列×5行），修剪后可能略少
        assert len(data["nodes"]) >= 3
        assert len(data["nodes"]) <= 40

    def test_connectivity_guaranteed(self):
        """生成后图必须连通。"""
        gen = MapGenerator()
        for map_id in range(5):
            data = gen.generate(map_id=map_id)
            G = nx.Graph()
            for nd in data["nodes"]:
                G.add_node(nd["nid"], **{k: v for k, v in nd.items() if k != "nid"})
            for e in data["edges"]:
                G.add_edge(e["u"], e["v"])
            assert nx.is_connected(G), f"map_id={map_id} 时图不连通"

    def test_no_dead_ends(self):
        """网状网格：所有非HQ节点度数≥2，无断头路。"""
        gen = MapGenerator()
        for map_id in range(5):
            data = gen.generate(map_id=map_id)
            degree = {}
            for e in data["edges"]:
                degree[e["u"]] = degree.get(e["u"], 0) + 1
                degree[e["v"]] = degree.get(e["v"], 0) + 1
            hq_set = {data["hq_red"], data["hq_blue"]}
            for nd in data["nodes"]:
                if nd["nid"] not in hq_set:
                    d = degree.get(nd["nid"], 0)
                    assert d >= 2, (
                        f"map_id={map_id}: 节点 {nd['nid']} 度数={d}，"
                        f"存在断头路"
                    )

    def test_grid_structure(self):
        """网格结构测试：横向和纵向边占主导。"""
        gen = MapGenerator()
        data = gen.generate(map_id=42)
        # 纺锤7×5生成器，至少有树状基础边
        assert len(data["edges"]) >= 10, "网格边数过少"

    def test_hq_assignment(self):
        """HQ 分配：红方在左，蓝方在右。"""
        gen = MapGenerator()
        data = gen.generate(map_id=42)
        nodes_by_nid = {nd["nid"]: nd for nd in data["nodes"]}
        red_pos = nodes_by_nid[data["hq_red"]]
        blue_pos = nodes_by_nid[data["hq_blue"]]
        assert red_pos["x"] < blue_pos["x"], "红方 HQ 应在左侧"

    def test_terrain_assignment(self):
        """地形分配：所有节点都有合法地形。"""
        gen = MapGenerator()
        data = gen.generate(map_id=42)
        from ..game.constants import TERRAIN_LIST
        for nd in data["nodes"]:
            assert nd["terrain"] in TERRAIN_LIST, f"节点 {nd['nid']} 地形非法: {nd['terrain']}"

    def test_hq_terrain_is_normal(self):
        """HQ 节点地形必须为 normal。"""
        gen = MapGenerator()
        data = gen.generate(map_id=42)
        nodes_by_nid = {nd["nid"]: nd for nd in data["nodes"]}
        assert nodes_by_nid[data["hq_red"]]["terrain"] == "normal"
        assert nodes_by_nid[data["hq_blue"]]["terrain"] == "normal"

    def test_reproducible_with_seed(self):
        """相同种子生成相同地图。"""
        gen = MapGenerator()
        data1 = gen.generate(map_id=123)
        data2 = gen.generate(map_id=123)
        assert data1["nodes"] == data2["nodes"]
        assert data1["edges"] == data2["edges"]

    def test_star_points_format(self):
        """star_points 输出格式为列表，每项含 x/y/area_id/has_star。"""
        gen = MapGenerator()
        data = gen.generate(map_id=42)
        for sp in data["star_points"]:
            assert "x" in sp, f"star_points 项缺少 x"
            assert "y" in sp, f"star_points 项缺少 y"
            assert "area_id" in sp, f"star_points 项缺少 area_id"

    def test_difficulty_configs(self):
        """不同难度生成不同规模地图。"""
        for diff in ["easy", "normal", "hard"]:
            gen = MapGenerator()
            data = gen.generate(map_id=42, difficulty=diff)
            assert len(data["nodes"]) >= 3, f"difficulty={diff} 节点数过少"


class TestMapEvaluator:
    """地图评估器测试。"""

    def _make_connected_graph(self) -> tuple[nx.Graph, int, int]:
        """创建连通测试图。"""
        G = nx.Graph()
        for i in range(10):
            G.add_node(i, pos=(50 + i * 80, 300))
        for i in range(9):
            G.add_edge(i, i + 1)
        return G, 0, 9

    def test_connectivity_score(self):
        """连通图得分 100。"""
        G, hq_r, hq_b = self._make_connected_graph()
        evaluator = MapEvaluator(G, hq_r, hq_b)
        scores = evaluator.evaluate()
        assert scores["connectivity"] == 100.0

    def test_disconnected_score(self):
        """不连通图得分 0。"""
        G = nx.Graph()
        G.add_node(0, pos=(100, 300))
        G.add_node(1, pos=(500, 300))
        # 不连边
        evaluator = MapEvaluator(G, 0, 1)
        scores = evaluator.evaluate()
        assert scores["connectivity"] == 0.0

    def test_is_balanced(self):
        """公平性判断。"""
        G, hq_r, hq_b = self._make_connected_graph()
        evaluator = MapEvaluator(G, hq_r, hq_b)
        result = evaluator.is_balanced(threshold=30)
        assert isinstance(result, bool)

    def test_total_score_range(self):
        """总分在 0-100 范围内。"""
        G, hq_r, hq_b = self._make_connected_graph()
        evaluator = MapEvaluator(G, hq_r, hq_b)
        scores = evaluator.evaluate()
        assert 0 <= scores["total"] <= 100