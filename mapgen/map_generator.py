# ==============================================================
# 玩具大乱斗 - 纺锤型地图自动生成器 (自然树状分支与聚合增强版)
#
# 核心算法升级：
#   - 分层段落采样：打破严格网格，中心地块呈现高度随机且有机的错落分布
#   - 树状就近连通：从基地发散 -> 中间战场交替耦合 -> 敌方基地收束
#   - 删减冗余连线：拒绝蜘蛛网式的全连通，呈现正常的战棋战线与隘口
# ==============================================================

import json
import math
import random
from pathlib import Path
from typing import Dict, List, Tuple

# 使用 constants 中的统一地形权重，而非本地硬编码
from game.constants import TERRAIN_WEIGHTS as CONST_TERRAIN_WEIGHTS


class MapGenerator:
    """玩具大乱斗 - 有机纺锤型（左小中大右小）战棋地图自动生成器"""

    def __init__(self, cols: int = 7, rows: int = 5,
                 spacing_x: float = 130.0, spacing_y: float = 110.0,
                 *args, **kwargs):
        """支持 cols/rows 战线参数，同时兼容旧版关键字传参不报错"""
        self.cols = cols
        self.rows = rows
        self.spacing_x = spacing_x
        self.spacing_y = spacing_y
        self.center_c = (cols - 1) / 2.0
        
        # 旧版参数安全吸收
        self.node_count = kwargs.get("node_count", 24)
        self.min_node = kwargs.get("min_node", 18)
        self.max_node = kwargs.get("max_node", 26)

    def _pick_terrain(self, is_hq: bool = False) -> str:
        """按权重随机选择地形，HQ 强制为 normal"""
        if is_hq:
            return "normal"
        terrains = list(CONST_TERRAIN_WEIGHTS.keys())
        weights = list(CONST_TERRAIN_WEIGHTS.values())
        return random.choices(terrains, weights=weights, k=1)[0]

    def generate(self, map_id: int = 1, difficulty: str = "normal") -> dict:
        """生成完整地图数据（树状分支连通 + 有机随机排布）"""
        random.seed(map_id)
        nodes = {}
        nodes_by_col = {}  # 记录每一列生成的节点，用于后续树状建边
        nid_counter = 0

        # ─── 1. 有机节点生成：纺锤形数量分配 + 空间随机漂移 ───
        
        # 预设画布居中基准
        start_x = 160.0
        total_height = self.rows * self.spacing_y
        start_y = 150.0

        for c in range(self.cols):
            nodes_by_col[c] = []
            
            # 计算当前列应当拥有的地块数量（纺锤形：两头少，中间多）
            if c == 0 or c == self.cols - 1:
                num_nodes = 1
            else:
                # 距离中心的归一化比例 (0.0 为中心, 1.0 为边缘)
                dx = abs(c - self.center_c) / self.center_c
                # 使用平滑曲线计算节点数，中心最多允许 self.rows 个
                base_nodes = self.rows * (1.0 - math.pow(dx, 1.4))
                # 加入一定的随机起伏
                num_nodes = max(2, int(round(base_nodes + random.uniform(-0.6, 0.6))))

            # 将当前列的垂直空间按数量等分，然后在等分区间内随机乱跑
            segment_h = total_height / num_nodes
            
            for i in range(num_nodes):
                is_hq = (c == 0 or c == self.cols - 1)
                
                # 计算 Y 坐标 (打破行阵列：段落内 20%~80% 区间随机浮动)
                if is_hq:
                    y = start_y + total_height / 2.0  # 基地严格居中
                else:
                    y = start_y + i * segment_h + random.uniform(segment_h * 0.2, segment_h * 0.8)

                # 计算 X 坐标 (中心地带增加左右参差错落感)
                x = start_x + c * self.spacing_x
                if not is_hq:
                    x += random.uniform(-25.0, 25.0)

                nd = {
                    "nid": nid_counter,
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "terrain": self._pick_terrain(is_hq=is_hq),
                    "is_hq": is_hq,
                    "hq_owner": "red" if c == 0 else ("blue" if c == self.cols - 1 else ""),
                    "area_id": 1 + (c % 3)  # 战区划分
                }
                nodes[nid_counter] = nd
                nodes_by_col[c].append(nd)
                nid_counter += 1

        # ─── 2. 提取 HQ 基地 ID ───
        hq_red = nodes_by_col[0][0]["nid"]
        hq_blue = nodes_by_col[self.cols - 1][0]["nid"]

        # ─── 3. 树状分支与聚合建边算法 (核心) ───
        edges = set()

        def add_edge(u, v):
            if u != v:
                edges.add((min(u, v), max(u, v)))

        # 逐列推进，构建前后联系
        for c in range(self.cols - 1):
            col_curr = nodes_by_col[c]
            col_next = nodes_by_col[c + 1]

            # 3.1 前向开枝 (Forward Branching)：当前列每个节点，必须连向下一列离它 Y 轴最近的点
            for u in col_curr:
                closest_v = min(col_next, key=lambda v: abs(u['y'] - v['y']) + abs(u['x'] - v['x'])*0.2)
                add_edge(u['nid'], closest_v['nid'])

            # 3.2 后向聚合 (Backward Merging)：下一列每个节点，必须连回前一列离它最近的点 (防止死路)
            for v in col_next:
                closest_u = min(col_curr, key=lambda u: abs(u['y'] - v['y']) + abs(u['x'] - v['x'])*0.2)
                add_edge(closest_u['nid'], v['nid'])

            # 3.3 适度破局 (Cross Links)：20% 几率跨接其他节点，形成小回环路，增加战术迂回
            if 0 < c < self.cols - 2:
                for u in col_curr:
                    if random.random() < 0.20:
                        # 挑选还没相连的候选节点
                        candidates = [v for v in col_next if (min(u['nid'], v['nid']), max(u['nid'], v['nid'])) not in edges]
                        if candidates:
                            v = random.choice(candidates)
                            add_edge(u['nid'], v['nid'])

            # 3.4 同列互联 (Vertical Links)：25% 几率将同一列上下相邻的点连起来，形成阵线防线
            if 0 < c < self.cols - 1 and len(col_curr) > 1:
                # 按照 y 坐标从上到下排序
                col_curr_sorted = sorted(col_curr, key=lambda n: n['y'])
                for i in range(len(col_curr_sorted) - 1):
                    if random.random() < 0.25:
                        add_edge(col_curr_sorted[i]['nid'], col_curr_sorted[i+1]['nid'])

        # ─── 4. 随机生成 4 个勋章争夺点位 ───
        star_points = []
        middle_nodes = [nd for nd in nodes.values() if not nd["is_hq"]]
        random.shuffle(middle_nodes)
        for i, nd in enumerate(middle_nodes[:4]):
            star_points.append({
                "x": nd["x"],
                "y": nd["y"],
                "area_id": i + 1,
                "has_star": True
            })

        return {
            "version": "1.0",
            "map_id": map_id,
            "difficulty": difficulty,
            "hq_red": hq_red,
            "hq_blue": hq_blue,
            "nodes": list(nodes.values()),
            "edges": [{"u": u, "v": v} for u, v in sorted(edges)],
            "star_points": star_points
        }

    # ─── 模板派生（兼容旧接口） ────────────────────────────

    def generate_from_template(self, template_path: str, seed: int = None) -> dict:
        if seed is not None:
            random.seed(seed)
        with open(template_path, "r", encoding="utf-8") as f:
            template = json.load(f)
        return self.generate(
            map_id=template.get("map_id", 1),
            difficulty=template.get("difficulty", "normal")
        )

    # ─── 导出方法 ──────────────────────────────────────────

    def export_to_file(self, output_path: str | Path, map_id: int = 1) -> Path:
        data = self.generate(map_id=map_id)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    @staticmethod
    def to_json(map_data: dict, filepath: str | Path) -> Path:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(map_data, f, ensure_ascii=False, indent=2)
        return path