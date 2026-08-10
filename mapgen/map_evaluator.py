"""
地图公平性评估器（改进版）。

评估维度：
- 连通性：图是否连通
- HQ 距离：双方 HQ 的图距离是否合理
- 对称性：双方区域大小是否均衡
- 区域均衡：KMeans 聚类后两区域节点数比
- 速攻风险：HQ 间是否存在过短路径

改进：
- lru_cache 缓存 count_kstep 结果
- 评分归一化到 0-100
"""

import math
import logging
from functools import lru_cache

import networkx as nx

logger = logging.getLogger(__name__)


class MapEvaluator:
    """地图公平性评估器。

    Attributes:
        G: 待评估的 networkx 图
        hq_red: 红方 HQ 节点 ID
        hq_blue: 蓝方 HQ 节点 ID
    """

    def __init__(self, G: nx.Graph, hq_red: int, hq_blue: int):
        self.G = G
        self.hq_red = hq_red
        self.hq_blue = hq_blue

    def evaluate(self) -> dict:
        """综合评估地图公平性。

        Returns:
            评估结果字典，包含各维度分数和总分
        """
        scores = {}
        scores["connectivity"] = self._score_connectivity()
        scores["hq_distance"] = self._score_hq_distance()
        scores["symmetry"] = self._score_symmetry()
        scores["region_balance"] = self._score_region_balance()
        scores["rush_risk"] = self._score_rush_risk()

        # 加权总分
        weights = {
            "connectivity": 0.25,
            "hq_distance": 0.20,
            "symmetry": 0.20,
            "region_balance": 0.20,
            "rush_risk": 0.15,
        }
        total = sum(scores[k] * weights[k] for k in scores)
        scores["total"] = round(total, 1)

        logger.info(f"地图评估: {scores}")
        return scores

    def _score_connectivity(self) -> float:
        """连通性评分。连通=100，不连通=0。"""
        return 100.0 if nx.is_connected(self.G) else 0.0

    def _score_hq_distance(self) -> float:
        """HQ 距离评分。

        图距离越接近总节点数的 40% 越好，过近或过远扣分。
        """
        try:
            dist = nx.shortest_path_length(self.G, self.hq_red, self.hq_blue)
        except nx.NetworkXNoPath:
            return 0.0

        n = self.G.number_of_nodes()
        ideal = n * 0.4
        # 高斯衰减：距离越接近 ideal 分越高
        score = 100 * math.exp(-0.5 * ((dist - ideal) / (ideal * 0.5)) ** 2)
        return round(max(0, min(100, score)), 1)

    def _score_symmetry(self) -> float:
        """对称性评分。

        以 HQ 中点为界，比较两侧节点数比例。
        """
        nodes = dict(self.G.nodes(data=True))
        if not nodes:
            return 0.0

        # 获取 HQ 坐标
        pos_red = nodes[self.hq_red].get("pos", (0, 0))
        pos_blue = nodes[self.hq_blue].get("pos", (0, 0))

        # 分界线 x 坐标
        mid_x = (pos_red[0] + pos_blue[0]) / 2

        left_count = 0
        right_count = 0
        for nid, data in nodes.items():
            x = data.get("pos", (0, 0))[0]
            if x < mid_x:
                left_count += 1
            else:
                right_count += 1

        total = left_count + right_count
        if total == 0:
            return 0.0

        # 比例越接近 50:50 分越高
        ratio = min(left_count, right_count) / total
        score = ratio * 200  # 50% → 100分
        return round(max(0, min(100, score)), 1)

    def _score_region_balance(self) -> float:
        """区域均衡评分。

        用 BFS 从两个 HQ 出发，比较各 k 步可达节点数。
        """
        max_k = 3
        red_counts = self._count_kstep(self.hq_red, max_k)
        blue_counts = self._count_kstep(self.hq_blue, max_k)

        diffs = []
        for k in range(1, max_k + 1):
            r = red_counts.get(k, 0)
            b = blue_counts.get(k, 0)
            total = r + b
            if total > 0:
                diffs.append(abs(r - b) / total)

        avg_diff = sum(diffs) / len(diffs) if diffs else 1.0
        score = (1 - avg_diff) * 100
        return round(max(0, min(100, score)), 1)

    @lru_cache(maxsize=32)
    def _count_kstep(self, source: int, max_k: int) -> dict[int, int]:
        """计算从 source 出发各 k 步可达节点数（缓存版）。

        Args:
            source: 起始节点
            max_k: 最大步数

        Returns:
            {k: count} 字典
        """
        result = {}
        visited = {source}
        frontier = {source}

        for k in range(1, max_k + 1):
            next_frontier = set()
            for node in frontier:
                for neighbor in self.G.neighbors(node):
                    if neighbor not in visited:
                        next_frontier.add(neighbor)
                        visited.add(neighbor)
            result[k] = len(next_frontier)
            frontier = next_frontier

        return result

    def _score_rush_risk(self) -> float:
        """速攻风险评分。

        HQ 间最短路径过短则扣分。
        """
        try:
            dist = nx.shortest_path_length(self.G, self.hq_red, self.hq_blue)
        except nx.NetworkXNoPath:
            return 100.0  # 不可达=无速攻风险

        n = self.G.number_of_nodes()
        # 距离 < 总节点数 15% 认为有速攻风险
        threshold = n * 0.15
        if dist >= threshold:
            return 100.0

        # 线性扣分
        score = (dist / threshold) * 100
        return round(max(0, min(100, score)), 1)

    def is_balanced(self, threshold: float = 60.0) -> bool:
        """判断地图是否公平。

        Args:
            threshold: 总分阈值

        Returns:
            总分 >= threshold 则为公平
        """
        result = self.evaluate()
        return result["total"] >= threshold