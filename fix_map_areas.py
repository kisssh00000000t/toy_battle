"""fix_map_areas.py — 将地图 area_id 重新划分为4组。"""
import json, sys
from pathlib import Path

def fix_map(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = data["nodes"]
    # 按 x 坐标排序后均匀分4组
    sorted_nodes = sorted(nodes, key=lambda n: (n.get("x", 0), n.get("y", 0)))
    n = len(sorted_nodes)
    for i, node in enumerate(sorted_nodes):
        node["area_id"] = 1 + (i * 4 // n)  # 均匀分4组
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    areas = set(nd["area_id"] for nd in nodes)
    print(f"{path}: {n} nodes, areas={sorted(areas)}")

for m in sys.argv[1:]:
    fix_map(m)