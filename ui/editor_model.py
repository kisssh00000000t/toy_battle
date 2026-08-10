"""
编辑器数据模型。

独立于游戏 Board，管理节点/边/HQ 的增删改查，
内置撤销/重做操作栈，支持 JSON 序列化。
"""

import json
import copy
import logging
from pathlib import Path
from typing import Optional, Dict, Set, List, Tuple

import networkx as nx

from game.constants import TERRAIN_LIST

logger = logging.getLogger(__name__)

# 节点数据: {"x": float, "y": float, "terrain": str}
NodeData = Dict[str, object]
# 边: (u, v) 且 u < v
Edge = Tuple[int, int]


class EditorModel:
    """编辑器数据模型，独立于游戏 Board。

    内部用字典存储节点和边，不依赖 networkx，
    但可导出为 networkx Graph 供 MapEvaluator 使用。

    Attributes:
        nodes: {nid: {"x": float, "y": float, "terrain": str}}
        edges: set of (u, v) tuples, u < v
        hq_red: 红方 HQ 节点 ID
        hq_blue: 蓝方 HQ 节点 ID
        next_nid: 下一个可用节点 ID
        map_id: 地图ID
        difficulty: 难度
        caribbean_mode: 加勒比双蓝HQ模式
        medal_goal: 勋章目标数
        background: 背景预设名
    """

    MAX_UNDO = 50

    def __init__(self):
        self.nodes: Dict[int, NodeData] = {}
        self.edges: Set[Edge] = set()
        self.hq_red: Optional[int] = None
        self.hq_blue: Optional[int] = None
        self.next_nid: int = 0
        self.star_points: list = []  # [{x, y, area_id, has_star}, ...]
        # 标准元数据
        self.map_id: int = 0
        self.difficulty: str = "normal"
        self.caribbean_mode: bool = False
        self.medal_goal: int = 3
        self.background: str = "bg_dark"
        # 撤销/重做栈
        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []

    # ─── 状态快照（撤销/重做）────────────────────────────────

    def _snapshot(self) -> dict:
        """拍摄当前状态快照。"""
        return {
            "nodes": copy.deepcopy(self.nodes),
            "edges": set(self.edges),           # set 可直接 copy
            "hq_red": self.hq_red,
            "hq_blue": self.hq_blue,
            "next_nid": self.next_nid,
            "star_points": copy.deepcopy(self.star_points),
            "map_id": self.map_id,
            "difficulty": self.difficulty,
            "caribbean_mode": self.caribbean_mode,
            "medal_goal": self.medal_goal,
            "background": self.background,
        }

    def _restore(self, state: dict) -> None:
        """从快照恢复状态。"""
        self.nodes = copy.deepcopy(state["nodes"])
        self.edges = set(state["edges"])
        self.hq_red = state["hq_red"]
        self.hq_blue = state["hq_blue"]
        self.next_nid = state["next_nid"]
        self.star_points = copy.deepcopy(state.get("star_points", []))
        self.map_id = state.get("map_id", 0)
        self.difficulty = state.get("difficulty", "normal")
        self.caribbean_mode = state.get("caribbean_mode", False)
        self.medal_goal = state.get("medal_goal", 3)
        self.background = state.get("background", "bg_dark")

    def push_state(self) -> None:
        """保存当前状态到撤销栈（在修改操作前调用）。"""
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """撤销，返回是否成功。"""
        if not self._undo_stack:
            return False
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        return True

    def redo(self) -> bool:
        """重做，返回是否成功。"""
        if not self._redo_stack:
            return False
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        return True

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    # ─── 节点操作 ────────────────────────────────────────────

    def add_node(self, x: float, y: float, terrain: str = "normal") -> int:
        """在指定位置创建新节点，返回节点 ID。"""
        nid = self.next_nid
        while nid in self.nodes:
            nid += 1
        self.nodes[nid] = {"x": x, "y": y, "terrain": terrain}
        self.next_nid = nid + 1
        return nid

    def delete_node(self, nid: int) -> None:
        """删除节点及其所有连边。"""
        if nid not in self.nodes:
            return
        # 删除关联边
        self.edges = {(u, v) for u, v in self.edges if u != nid and v != nid}
        del self.nodes[nid]
        # 清理 HQ 引用
        if self.hq_red == nid:
            self.hq_red = None
        if self.hq_blue == nid:
            self.hq_blue = None

    def move_node(self, nid: int, x: float, y: float) -> None:
        """移动节点位置。"""
        if nid in self.nodes:
            self.nodes[nid]["x"] = x
            self.nodes[nid]["y"] = y

    def set_terrain(self, nid: int, terrain: str) -> None:
        """设置节点地形。"""
        if nid in self.nodes:
            self.nodes[nid]["terrain"] = terrain

    def get_node(self, nid: int) -> Optional[NodeData]:
        """获取节点数据。"""
        return self.nodes.get(nid)

    def node_pos(self, nid: int) -> Optional[Tuple[float, float]]:
        """获取节点坐标。"""
        nd = self.nodes.get(nid)
        if nd:
            return (nd["x"], nd["y"])
        return None

    # ─── 边操作 ──────────────────────────────────────────────

    @staticmethod
    def _normalize_edge(u: int, v: int) -> Edge:
        """规范化边：保证 u < v。"""
        return (min(u, v), max(u, v))

    def add_edge(self, u: int, v: int) -> bool:
        """添加边，返回是否新增（已存在返回 False）。"""
        if u == v or u not in self.nodes or v not in self.nodes:
            return False
        edge = self._normalize_edge(u, v)
        if edge in self.edges:
            return False
        self.edges.add(edge)
        return True

    def remove_edge(self, u: int, v: int) -> bool:
        """删除边，返回是否成功。"""
        edge = self._normalize_edge(u, v)
        if edge in self.edges:
            self.edges.discard(edge)
            return True
        return False

    def has_edge(self, u: int, v: int) -> bool:
        """判断边是否存在。"""
        return self._normalize_edge(u, v) in self.edges

    def node_neighbors(self, nid: int) -> List[int]:
        """获取节点的所有邻居。"""
        neighbors = []
        for u, v in self.edges:
            if u == nid:
                neighbors.append(v)
            elif v == nid:
                neighbors.append(u)
        return neighbors

    # ─── HQ 操作 ─────────────────────────────────────────────

    def set_hq_red(self, nid: Optional[int]) -> None:
        """设置红方 HQ。nid 为 None 则取消。"""
        if nid is not None and nid in self.nodes:
            self.nodes[nid]["terrain"] = "normal"
        self.hq_red = nid

    def set_hq_blue(self, nid: Optional[int]) -> None:
        """设置蓝方 HQ。nid 为 None 则取消。"""
        if nid is not None and nid in self.nodes:
            self.nodes[nid]["terrain"] = "normal"
        self.hq_blue = nid

    # ─── 序列化 ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        """导出为地图数据字典（兼容 MapGenerator 输出格式，含标准字段）。"""
        nodes_list = []
        for nid, nd in self.nodes.items():
            nodes_list.append({
                "nid": nid,
                "x": nd["x"],
                "y": nd["y"],
                "terrain": nd.get("terrain", "normal"),
            })
        edges_list = [{"u": u, "v": v} for u, v in sorted(self.edges)]
        return {
            "nodes": nodes_list,
            "edges": edges_list,
            "hq_red": self.hq_red,
            "hq_blue": self.hq_blue,
            "star_points": self.star_points,
            # 标准元数据
            "map_id": self.map_id,
            "difficulty": self.difficulty,
            "caribbean_mode": self.caribbean_mode,
            "medal_goal": self.medal_goal,
            "node_count": len(self.nodes),
            "background": self.background,
        }

    def load_from_dict(self, data: dict) -> None:
        """从地图数据字典加载（兼容 list 和 dict 两种 nodes 格式）。"""
        self.nodes.clear()
        self.edges.clear()
        self.hq_red = data.get("hq_red")
        self.hq_blue = data.get("hq_blue")
        # 加载标准元数据
        self.map_id = data.get("map_id", 0)
        self.difficulty = data.get("difficulty", "normal")
        self.caribbean_mode = data.get("caribbean_mode", False)
        self.medal_goal = data.get("medal_goal", 3)
        self.background = data.get("background", "bg_dark")
        # 加载节点
        nodes_data = data.get("nodes", {})
        if isinstance(nodes_data, list):
            for nd in nodes_data:
                nid = int(nd["nid"])
                self.nodes[nid] = {
                    "x": nd["x"], "y": nd["y"],
                    "terrain": nd.get("terrain", "normal"),
                }
        else:
            for nid_str, ndata in nodes_data.items():
                nid = int(nid_str)
                self.nodes[nid] = {
                    "x": ndata["x"], "y": ndata["y"],
                    "terrain": ndata.get("terrain", "normal"),
                }
        # 加载边
        for e in data.get("edges", []):
            u = e["u"] if isinstance(e, dict) else e[0]
            v = e["v"] if isinstance(e, dict) else e[1]
            self.edges.add(self._normalize_edge(int(u), int(v)))
        # 更新 next_nid
        if self.nodes:
            self.next_nid = max(self.nodes.keys()) + 1
        else:
            self.next_nid = 0
        # 加载星星点位
        self.star_points = copy.deepcopy(data.get("star_points", []))

    def save_json(self, path: str = "custom_map.json") -> str:
        """保存到 JSON 文件，返回路径。"""
        data = self.to_dict()
        save_path = Path(path)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"地图已保存到 {save_path}")
        return str(save_path)

    def load_json(self, path: str = "custom_map.json") -> bool:
        """从 JSON 文件加载，返回是否成功。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.load_from_dict(data)
            return True
        except FileNotFoundError:
            return False

    def clear(self) -> None:
        """清空所有数据。"""
        self.nodes.clear()
        self.edges.clear()
        self.hq_red = None
        self.hq_blue = None
        self.next_nid = 0
        self.star_points = []
        self.map_id = 0
        self.difficulty = "normal"
        self.caribbean_mode = False
        self.medal_goal = 3
        self.background = "bg_dark"
        self._undo_stack.clear()
        self._redo_stack.clear()

    # ─── networkx 兼容 ──────────────────────────────────────

    def to_graph(self) -> nx.Graph:
        """导出为 networkx Graph（供 MapEvaluator 使用）。"""
        G = nx.Graph()
        for nid, nd in self.nodes.items():
            G.add_node(nid, pos=(nd["x"], nd["y"]), terrain=nd.get("terrain", "normal"))
        for u, v in self.edges:
            G.add_edge(u, v)
        return G

    # ─── 查询 ────────────────────────────────────────────────

    def find_node_at(self, x: float, y: float, radius: float) -> Optional[int]:
        """查找指定坐标范围内的节点（AABB矩形碰撞），返回最近的节点 ID 或 None。"""
        best_nid = None
        best_dist = radius + 1
        for nid, nd in self.nodes.items():
            dx = abs(nd["x"] - x)
            dy = abs(nd["y"] - y)
            if dx <= radius and dy <= radius:
                dist = (dx ** 2 + dy ** 2) ** 0.5
                if dist < best_dist:
                    best_nid = nid
                    best_dist = dist
        return best_nid

    # ─── 星星操作 ────────────────────────────────────────────

    STAR_CLICK_RADIUS = 20.0  # 星星点击判定半径（世界坐标）

    def add_star_point(self, x: float, y: float, area_id: int = -1) -> int:
        """在指定位置添加星星点位，返回索引。

        Args:
            x: 世界坐标 X
            y: 世界坐标 Y
            area_id: 所属区域 ID，-1 表示未分配

        Returns:
            新添加的星星在 star_points 列表中的索引
        """
        sp = {"x": x, "y": y, "area_id": area_id, "has_star": True}
        self.star_points.append(sp)
        return len(self.star_points) - 1

    def remove_star_point(self, index: int) -> bool:
        """删除指定索引的星星点位，返回是否成功。"""
        if 0 <= index < len(self.star_points):
            self.star_points.pop(index)
            return True
        return False

    def find_star_at(self, x: float, y: float, radius: float = None) -> Optional[int]:
        """查找指定坐标范围内的星星点位索引。

        Args:
            x: 世界坐标 X
            y: 世界坐标 Y
            radius: 判定半径，默认 STAR_CLICK_RADIUS

        Returns:
            星星在 star_points 中的索引，未找到返回 None
        """
        if radius is None:
            radius = self.STAR_CLICK_RADIUS
        best_idx = None
        best_dist = radius + 1
        for i, sp in enumerate(self.star_points):
            dx = abs(sp["x"] - x)
            dy = abs(sp["y"] - y)
            if dx <= radius and dy <= radius:
                dist = (dx ** 2 + dy ** 2) ** 0.5
                if dist < best_dist:
                    best_idx = i
                    best_dist = dist
        return best_idx