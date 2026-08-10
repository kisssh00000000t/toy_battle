"""
不规则图棋盘模型。

棋盘由节点（BoardNode）和边（邻接关系）组成，支持 BFS 连通判定。
"""

from collections import deque
from .constants import TERRAIN_DATA, NODE_CLICK_RADIUS


class BoardNode:
    """棋盘节点。

    Attributes:
        nid: 节点唯一ID
        x, y: 屏幕坐标（用于渲染）
        terrain_key: 地形类型键
        stack: 驻军堆叠（底层先放，顶层为当前控制单位）
        is_hq: 是否为总部节点
        hq_owner: 总部归属（"red"/"blue"/None）
        area_id: 所属区域ID（用于勋章判定）
    """

    def __init__(self, nid: int, x: float, y: float, terrain_key: str,
                 is_hq: bool, hq_owner: str | None, area_id: int):
        self.nid = nid
        self.x = x
        self.y = y
        self.terrain_key = terrain_key
        self.stack: list = []
        self.is_hq = is_hq
        self.hq_owner = hq_owner
        self.area_id = area_id

    @property
    def top_troop(self):
        """堆叠顶层的兵种单位，空节点返回 None。"""
        return self.stack[-1] if self.stack else None

    def is_controlled_by(self, owner: str) -> bool:
        """判断节点是否被指定玩家控制。

        HQ 节点始终由其归属方控制；普通节点由顶层驻军归属方控制。
        """
        if self.is_hq and self.hq_owner == owner:
            return True
        top = self.top_troop
        return top is not None and top.owner == owner

    def to_dict(self) -> dict:
        """序列化节点为字典（用于网络传输、存档、断线重连）。"""
        return {
            "nid": self.nid,
            "x": self.x,
            "y": self.y,
            "terrain_key": self.terrain_key,
            "is_hq": self.is_hq,
            "hq_owner": self.hq_owner,
            "area_id": self.area_id,
            "stack": [
                {"key": t.troop_key, "owner": t.owner, "facedown": t.is_facedown}
                for t in self.stack
            ]
        }

    def load_stack_from_dict(self, stack_data: list) -> None:
        """从字典列表恢复驻军堆叠。"""
        from .troop import Troop
        self.stack.clear()
        for td in stack_data:
            t = Troop(td["key"], td["owner"])
            t.is_facedown = td.get("facedown", False)
            self.stack.append(t)


class GameBoard:
    """游戏棋盘，管理节点和邻接关系。

    Attributes:
        nodes: 节点字典 {nid: BoardNode}
        adj: 邻接表 {nid: [neighbor_nid, ...]}
        hq_map: 总部映射 {owner_color: [nid, ...]}
    """

    def __init__(self):
        self.nodes: dict[int, BoardNode] = {}
        self.adj: dict[int, list[int]] = {}
        self.hq_map: dict[str, list[int]] = {}
        self.area_centers: dict[int, list[float]] = {}  # {area_id: [cx, cy]}
        self.star_points: list[dict] = []  # [{x, y, area_id, has_star}, ...]

    def to_dict(self) -> dict:
        """序列化棋盘为字典（用于回放存档、联网同步）。

        输出格式与 load_from_dict 输入格式完全兼容。
        """
        nodes = []
        for nid, node in self.nodes.items():
            nodes.append({
                "nid": node.nid,
                "x": node.x,
                "y": node.y,
                "terrain": node.terrain_key,
                "is_hq": node.is_hq,
                "hq_owner": node.hq_owner,
                "area_id": node.area_id,
            })
        edges = []
        seen = set()
        for u, neighbors in self.adj.items():
            for v in neighbors:
                key = (min(u, v), max(u, v))
                if key not in seen:
                    seen.add(key)
                    edges.append({"u": u, "v": v})
        return {
            "nodes": nodes,
            "edges": edges,
            "area_centers": self.area_centers,
            "star_points": self.star_points,
        }

    def load_from_dict(self, map_data: dict) -> None:
        """从地图数据字典加载棋盘。

        Args:
            map_data: 包含 nodes 和 edges 的地图数据
        """
        self.nodes.clear()
        self.adj.clear()
        self.hq_map.clear()
        for nd in map_data["nodes"]:
            node = BoardNode(
                nid=nd["nid"],
                x=nd["x"], y=nd["y"],
                terrain_key=nd["terrain"],
                is_hq=nd["is_hq"],
                hq_owner=nd["hq_owner"],
                area_id=nd["area_id"]
            )
            self.nodes[node.nid] = node
            self.adj[node.nid] = []
            if node.is_hq:
                if node.hq_owner not in self.hq_map:
                    self.hq_map[node.hq_owner] = []
                self.hq_map[node.hq_owner].append(node.nid)
        for e in map_data["edges"]:
            u, v = e["u"], e["v"]
            self.adj[u].append(v)
            self.adj[v].append(u)
        # 加载区块中心坐标（可选，用于UI星星绘制）
        self.area_centers = {}
        for aid, center in map_data.get("area_centers", {}).items():
            self.area_centers[int(aid)] = center
        # 加载星星点位（可选，用于UI星星绘制）
        self.star_points = map_data.get("star_points", [])

    def get_node(self, nid: int) -> BoardNode | None:
        """按ID获取节点。"""
        return self.nodes.get(nid)

    def get_neighbors(self, nid: int) -> list[int]:
        """获取节点的邻居ID列表。"""
        return self.adj.get(nid, [])

    def get_node_by_pos(self, mx: float, my: float, radius: int = None) -> BoardNode | None:
        """按屏幕坐标查找节点（用于鼠标点击检测，AABB矩形碰撞）。

        Args:
            mx, my: 鼠标坐标（世界坐标）
            radius: 点击判定半尺寸，默认使用 NODE_CLICK_RADIUS
        """
        if radius is None:
            radius = NODE_CLICK_RADIUS
        half = radius
        for nid, node in self.nodes.items():
            if abs(node.x - mx) < half and abs(node.y - my) < half:
                return node
        return None

    def bfs_owned_reachable(self, start_nid: int, owner: str) -> set[int]:
        """BFS 查找从起点出发，沿己方控制节点可达的所有节点。

        规则出处：放置校验要求目标节点与己方 HQ 通过己方控制节点连通。

        Args:
            start_nid: 起始节点ID
            owner: 玩家颜色

        Returns:
            可达节点ID集合
        """
        visited: set[int] = set()
        q: deque[int] = deque([start_nid])
        visited.add(start_nid)
        while q:
            curr = q.popleft()
            for nb in self.get_neighbors(curr):
                if nb in visited:
                    continue
                nd = self.get_node(nb)
                if nd and nd.is_controlled_by(owner):
                    visited.add(nb)
                    q.append(nb)
        return visited

    def is_connected_to_hq(self, target_nid: int, owner: str) -> bool:
        """判断目标节点是否与己方 HQ 连通。

        目标节点无需被己方控制，只需与己方控制节点相邻即可放置。
        使用多源BFS从所有HQ同时出发，避免多次单源BFS。

        Args:
            target_nid: 目标节点ID
            owner: 玩家颜色

        Returns:
            是否连通
        """
        hq_list = self.hq_map.get(owner, [])
        # 多源BFS：所有HQ同时入队
        visited: set[int] = set()
        q: deque[int] = deque()
        for hq in hq_list:
            if hq not in visited:
                visited.add(hq)
                q.append(hq)
        while q:
            curr = q.popleft()
            for nb in self.get_neighbors(curr):
                if nb in visited:
                    continue
                nd = self.get_node(nb)
                if nd and nd.is_controlled_by(owner):
                    visited.add(nb)
                    q.append(nb)
        # 目标在可达集内（HQ本身或己方控制节点），或与可达节点相邻
        if target_nid in visited:
            return True
        for nid in visited:
            if target_nid in self.get_neighbors(nid):
                return True
        return False