"""
地图JSON加载器。

修复清单：
- FIX: random_valid_map 中 csv 变量名应为 csv_path
- FIX: 添加 CSV 不存在或无有效地图的回退方案
"""

import json
import csv
import random
import logging
from pathlib import Path

from game.constants import TERRAIN_KEY_ALIASES

logger = logging.getLogger(__name__)

# 默认地图目录
_DEFAULT_MAP_DIR = Path(__file__).parent.parent / "maps"


def load_map(map_dir: Path | None = None) -> dict:
    """加载地图的便捷函数。

    优先从指定目录加载有效地图，无地图时生成默认地图。

    Args:
        map_dir: 地图目录路径，默认为项目 maps 子目录

    Returns:
        地图数据字典
    """
    if map_dir is None:
        map_dir = _DEFAULT_MAP_DIR
    return MapLoader.random_valid_map(map_dir)


class MapLoader:
    """地图加载器，支持从JSON文件和CSV评估报告加载地图。"""

    @staticmethod
    def load_json(path: Path) -> dict:
        """从JSON文件加载地图数据。

        自动迁移旧版地形键名（如 cloud_castle → city_of_clouds）。

        Args:
            path: JSON文件路径

        Returns:
            地图数据字典
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 迁移旧版地形键名
        for nd in data.get("nodes", []):
            old_key = nd.get("terrain", "normal")
            if old_key in TERRAIN_KEY_ALIASES:
                nd["terrain"] = TERRAIN_KEY_ALIASES[old_key]
        # 迁移旧版 area_centers → star_points
        if "star_points" not in data and "area_centers" in data:
            star_points = []
            for aid, center in data["area_centers"].items():
                star_points.append({
                    "x": center[0] if isinstance(center, (list, tuple)) else center.get("x", 0),
                    "y": center[1] if isinstance(center, (list, tuple)) else center.get("y", 0),
                    "area_id": int(aid),
                    "has_star": True,
                })
            data["star_points"] = star_points
        return data

    @staticmethod
    def random_valid_map(map_dir: Path) -> dict:
        """从评估报告中随机选择一个有效地图加载。

        若CSV不存在或无有效地图，则回退到随机选择目录中的任意JSON文件。
        若目录中无任何JSON文件，则生成一个默认地图。

        Args:
            map_dir: 地图目录路径

        Returns:
            地图数据字典
        """
        csv_path = map_dir / "map_evaluation_report.csv"
        valid_ids: list[int] = []

        # 尝试从CSV读取有效地图ID
        if csv_path.exists():
            try:
                # FIX: 原代码使用 csv 变量名，应为 csv_path
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get("is_valid", "").lower() == "true":
                            valid_ids.append(int(row["map_id"]))
            except (KeyError, ValueError, IOError) as e:
                logger.warning(f"读取CSV评估报告失败: {e}，将使用回退方案")

        # 从有效ID中随机选择
        if valid_ids:
            mid = random.choice(valid_ids)
            target = map_dir / f"map_{mid:02d}.json"
            if target.exists():
                return MapLoader.load_json(target)

        # 回退方案1：随机选择目录中任意JSON文件
        json_files = sorted(map_dir.glob("map_*.json"))
        if json_files:
            target = random.choice(json_files)
            logger.info(f"无有效CSV或有效地图，回退加载: {target.name}")
            return MapLoader.load_json(target)

        # 回退方案2：生成默认地图
        logger.warning("地图目录为空，生成默认地图")
        return MapLoader._generate_default_map()

    @staticmethod
    def _generate_default_map() -> dict:
        """生成一个最小的默认地图（用于无地图文件时的回退）。

        Returns:
            包含2个HQ节点和1个普通节点的最小地图
        """
        nodes = [
            {"nid": 0, "x": 200, "y": 400, "terrain": "normal",
             "is_hq": True, "hq_owner": "red", "area_id": 0},
            {"nid": 1, "x": 600, "y": 400, "terrain": "normal",
             "is_hq": True, "hq_owner": "blue", "area_id": 1},
            {"nid": 2, "x": 400, "y": 300, "terrain": "normal",
             "is_hq": False, "hq_owner": None, "area_id": 0},
        ]
        edges = [
            {"u": 0, "v": 2},
            {"u": 1, "v": 2},
        ]
        return {
            "map_id": -1, "difficulty": "normal", "caribbean_mode": False,
            "node_count": 3, "star_win_goal": 2, "nodes": nodes, "edges": edges
        }