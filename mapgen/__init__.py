"""地图生成与评估模块。"""

import logging

from .map_generator import MapGenerator
from .map_evaluator import MapEvaluator

logger = logging.getLogger(__name__)


def batch_generate(n=12, output_dir=None, difficulty="normal",
                   caribbean_mode=False):
    """批量生成地图到指定目录。

    Args:
        n: 生成数量，默认12
        output_dir: 输出目录，默认为 mapgen/out_maps
        difficulty: 难度，默认 normal
        caribbean_mode: 加勒比双蓝HQ模式，默认 False

    Returns:
        生成的地图数据列表
    """
    import json
    from pathlib import Path
    from game.constants import MAP_WIDTH, MAP_HEIGHT

    if output_dir is None:
        output_dir = Path(__file__).parent / "out_maps"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    gen = MapGenerator(
        width=MAP_WIDTH,
        height=MAP_HEIGHT,
        difficulty=difficulty,
        caribbean_mode=caribbean_mode,
    )
    results = []
    for i in range(n):
        data = gen.generate()
        # 确保 map_id 正确
        data["map_id"] = i
        path = output_dir / f"map_{i + 1:02d}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        results.append(data)
    return results


def evaluate_batch(map_dir=None):
    """评估目录中所有地图的公平性。

    Args:
        map_dir: 地图目录，默认为 mapgen/out_maps

    Returns:
        评估结果列表 [(文件名, 总分), ...]
    """
    import networkx as nx
    from pathlib import Path
    from game.map_loader import MapLoader

    if map_dir is None:
        map_dir = Path(__file__).parent / "out_maps"
    else:
        map_dir = Path(map_dir)

    json_files = sorted(map_dir.glob("map_*.json"))
    results = []
    for jf in json_files:
        data = MapLoader.load_json(jf)
        G = nx.Graph()
        for nd in data["nodes"]:
            G.add_node(nd["nid"], pos=(nd["x"], nd["y"]), terrain=nd.get("terrain", "normal"))
        for e in data["edges"]:
            G.add_edge(e["u"], e["v"])
        hq_red = data.get("hq_red")
        hq_blue = data.get("hq_blue")
        if hq_red is not None and hq_blue is not None:
            ev = MapEvaluator(G, hq_red, hq_blue)
            score = ev.evaluate()
            results.append((jf.name, score.get("total", 0)))
    return results


def generate_and_filter(n=20, threshold=60.0, output_dir=None, keep_max=12,
                        difficulty="normal", caribbean_mode=False):
    """批量生成地图，评估筛选后保留合格地图。

    生成 n 张地图，评估每张的公平性分数，
    仅保留总分 >= threshold 的地图，最多保留 keep_max 张。
    最高分地图自动复制到 maps/ 目录。

    Args:
        n: 生成数量，默认20
        threshold: 合格阈值（总分），默认60.0
        output_dir: 输出目录，默认为 mapgen/out_maps
        keep_max: 最多保留数量，默认12
        difficulty: 难度，默认 normal
        caribbean_mode: 加勒比双蓝HQ模式，默认 False

    Returns:
        合格地图数据列表 [(文件名, 总分, 数据), ...]
    """
    import json
    import shutil
    import networkx as nx
    from pathlib import Path
    from game.constants import MAP_WIDTH, MAP_HEIGHT

    if output_dir is None:
        output_dir = Path(__file__).parent / "out_maps"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 清空旧地图
    for old in output_dir.glob("map_*.json"):
        old.unlink()

    gen = MapGenerator(
        width=MAP_WIDTH,
        height=MAP_HEIGHT,
        difficulty=difficulty,
        caribbean_mode=caribbean_mode,
    )

    qualified = []  # [(score, data), ...]
    attempts = 0
    max_attempts = n * 3  # 最多尝试3倍数量

    while len(qualified) < n and attempts < max_attempts:
        attempts += 1
        data = gen.generate()
        data["map_id"] = attempts - 1

        # 构建图用于评估
        G = nx.Graph()
        for nd in data["nodes"]:
            G.add_node(nd["nid"], pos=(nd["x"], nd["y"]), terrain=nd.get("terrain", "normal"))
        for e in data["edges"]:
            G.add_edge(e["u"], e["v"])

        hq_red = data.get("hq_red")
        hq_blue = data.get("hq_blue")
        if hq_red is None or hq_blue is None:
            continue

        ev = MapEvaluator(G, hq_red, hq_blue)
        result = ev.evaluate()
        total = result.get("total", 0)

        if total >= threshold:
            qualified.append((total, data))

    # 按分数降序排列，保留前 keep_max 张
    qualified.sort(key=lambda x: x[0], reverse=True)
    qualified = qualified[:keep_max]

    # 保存合格地图到 out_maps
    saved = []
    for i, (score, data) in enumerate(qualified):
        fname = f"map_{i + 1:02d}.json"
        path = output_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        saved.append((fname, score, data))

    # 将最高分地图复制到 maps/ 目录
    if saved:
        maps_dir = Path(__file__).parent.parent / "maps"
        maps_dir.mkdir(parents=True, exist_ok=True)
        best_fname, best_score, _ = saved[0]
        src = output_dir / best_fname
        dst = maps_dir / best_fname
        shutil.copy2(src, dst)
        logger.info(f"最高分地图 {best_fname} (评分={best_score:.1f}) 已复制到 maps/")

    return saved