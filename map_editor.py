"""
地图编辑器（Pygame 实现）。

功能：
- 可视化编辑地图节点、边、地形
- 支持撤销/重做（Undo/Redo）
- 保存/加载 JSON 地图
- 实时公平性评分显示

改进：
- 添加 UndoManager 支持撤销/重做
- 鼠标悬停显示节点信息
- 快捷键提示
"""

import json
import math
import logging
from pathlib import Path
from typing import Optional

import pygame
import networkx as nx

from .game.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    TERRAIN_LIST, TERRAIN_COLOR, TERRAIN_SYM,
    BG_COLOR,
    TILE_SQUARE_SIZE, TILE_ROUND_RADIUS,
)
from .mapgen.map_generator import MapGenerator
from .mapgen.map_evaluator import MapEvaluator

logger = logging.getLogger(__name__)


class UndoManager:
    """撤销/重做管理器。

    Attributes:
        undo_stack: 撤销栈
        redo_stack: 重做栈
        max_size: 最大历史记录数
    """

    def __init__(self, max_size: int = 50):
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.max_size = max_size

    def push(self, state: dict) -> None:
        """保存状态到撤销栈。"""
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.max_size:
            self.undo_stack.pop(0)
        # 新操作清空重做栈
        self.redo_stack.clear()

    def undo(self) -> Optional[dict]:
        """撤销，返回上一状态。"""
        if not self.undo_stack:
            return None
        state = self.undo_stack.pop()
        self.redo_stack.append(state)
        return state

    def redo(self) -> Optional[dict]:
        """重做，返回下一状态。"""
        if not self.redo_stack:
            return None
        state = self.redo_stack.pop()
        self.undo_stack.append(state)
        return state

    @property
    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0


class MapEditor:
    """地图编辑器主类。

    Attributes:
        screen: Pygame 显示表面
        clock: 帧率控制器
        graph: 当前编辑的图
        map_data: 地图数据
        undo_mgr: 撤销管理器
        selected_node: 当前选中节点
        selected_terrain: 当前选中地形
        hq_red: 红方 HQ
        hq_blue: 蓝方 HQ
    """

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("玩具大乱斗 - 地图编辑器")
        _icon_path = Path(__file__).parent.parent / "icon.png"
        if _icon_path.exists():
            pygame.display.set_icon(pygame.image.load(str(_icon_path)))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("simhei", 16)
        self.font_large = pygame.font.SysFont("simhei", 24)

        # 编辑状态
        self.graph: nx.Graph = nx.Graph()
        self.map_data: dict = {}
        self.undo_mgr = UndoManager()
        self.selected_node: Optional[int] = None
        self.selected_terrain: str = "normal"
        self.hq_red: Optional[int] = None
        self.hq_blue: Optional[int] = None
        self.dragging: Optional[int] = None
        self.hover_node: Optional[int] = None
        self.evaluation: dict = {}

        # 右键连线状态
        self.line_start_nid: Optional[int] = None
        self.is_drawing_line: bool = False

        # 工具栏
        self.toolbar_y = SCREEN_HEIGHT - 60
        self.terrain_buttons: list[dict] = []
        self._init_toolbar()

    def _init_toolbar(self) -> None:
        """初始化地形选择工具栏。"""
        x = 10
        for terrain in TERRAIN_LIST:
            rect = pygame.Rect(x, self.toolbar_y, 70, 40)
            self.terrain_buttons.append({
                "rect": rect,
                "terrain": terrain,
                "color": TERRAIN_COLOR.get(terrain, (200, 200, 200)),
            })
            x += 80

    def run(self) -> None:
        """编辑器主循环。"""
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    running = self._handle_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_click(event)
                elif event.type == pygame.MOUSEBUTTONUP:
                    self._handle_release(event)
                elif event.type == pygame.MOUSEMOTION:
                    self._handle_motion(event)

            self._draw()
            self.clock.tick(FPS)

        pygame.quit()

    def _handle_key(self, event: pygame.event.Event) -> bool:
        """处理键盘事件。返回是否继续运行。"""
        if event.key == pygame.K_z and pygame.key.get_mods() & pygame.KMOD_CTRL:
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self._redo()
            else:
                self._undo()
        elif event.key == pygame.K_n and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self._new_map()
        elif event.key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self._save_map()
        elif event.key == pygame.K_l and pygame.key.get_mods() & pygame.KMOD_CTRL:
            self._load_map()
        elif event.key == pygame.K_e:
            self._evaluate_map()
        elif event.key == pygame.K_ESCAPE:
            # ESC 取消连线或退出
            if self.is_drawing_line:
                self.line_start_nid = None
                self.is_drawing_line = False
            else:
                return False
        return True

    def _handle_click(self, event: pygame.event.Event) -> None:
        """处理鼠标点击。"""
        mx, my = event.pos

        # 右键：启动连线 / 取消连线
        if event.button == 3:
            node = self._find_node(mx, my)
            if node is not None:
                self.line_start_nid = node
                self.is_drawing_line = True
            else:
                # 右键空白处 → 取消连线
                if self.is_drawing_line:
                    self.line_start_nid = None
                    self.is_drawing_line = False
            return

        # 检查工具栏
        for btn in self.terrain_buttons:
            if btn["rect"].collidepoint(mx, my):
                self.selected_terrain = btn["terrain"]
                return

        # 左键
        if event.button != 1:
            return

        # 如果正在连线，左键点击节点完成连线
        if self.is_drawing_line and self.line_start_nid is not None:
            node = self._find_node(mx, my)
            if node is not None and node != self.line_start_nid:
                if not self.graph.has_edge(self.line_start_nid, node):
                    self._save_undo_state()
                    self.graph.add_edge(self.line_start_nid, node)
            self.line_start_nid = None
            self.is_drawing_line = False
            return

        # 检查节点
        node = self._find_node(mx, my)
        if node is not None:
            self.selected_node = node
            self.dragging = node
        # 注意：空白处点击不再创建节点（改由拖拽创建）

    def _handle_release(self, event: pygame.event.Event) -> None:
        """处理鼠标释放。"""
        self.dragging = None

    def _handle_motion(self, event: pygame.event.Event) -> None:
        """处理鼠标移动。"""
        mx, my = event.pos
        self.hover_node = self._find_node(mx, my)

        if self.dragging is not None and self.dragging in self.graph.nodes:
            self._save_undo_state()
            self.graph.nodes[self.dragging]["pos"] = (mx, my)

    def _find_node(self, mx: int, my: int) -> Optional[int]:
        """查找鼠标位置下的节点（AABB矩形碰撞）。"""
        half = TILE_SQUARE_SIZE // 2
        for nid, data in self.graph.nodes(data=True):
            pos = data.get("pos", (0, 0))
            if abs(mx - pos[0]) <= half and abs(my - pos[1]) <= half:
                return nid
        return None

    def _save_undo_state(self) -> None:
        """保存当前状态到撤销栈。"""
        state = {
            "nodes": dict(self.graph.nodes(data=True)),
            "edges": list(self.graph.edges()),
        }
        self.undo_mgr.push(state)

    def _undo(self) -> None:
        """撤销操作。"""
        state = self.undo_mgr.undo()
        if state:
            self._restore_state(state)

    def _redo(self) -> None:
        """重做操作。"""
        state = self.undo_mgr.redo()
        if state:
            self._restore_state(state)

    def _restore_state(self, state: dict) -> None:
        """恢复到指定状态。"""
        self.graph.clear()
        for nid, data in state["nodes"].items():
            self.graph.add_node(nid, **data)
        for u, v in state["edges"]:
            self.graph.add_edge(u, v)

    def _new_map(self) -> None:
        """生成新地图。"""
        gen = MapGenerator()
        self.map_data = gen.generate()
        self._load_map_data(self.map_data)

    def _load_map_data(self, data: dict) -> None:
        """从地图数据加载图。"""
        self.graph.clear()
        for nid, ndata in data["nodes"].items():
            self.graph.add_node(int(nid), pos=(ndata["x"], ndata["y"]), terrain=ndata.get("terrain", "normal"))
        for u, v in data["edges"]:
            self.graph.add_edge(int(u), int(v))
        self.hq_red = data.get("hq_red")
        self.hq_blue = data.get("hq_blue")

    def _save_map(self) -> None:
        """保存地图到 JSON。"""
        data = {
            "nodes": {},
            "edges": list(self.graph.edges()),
            "hq_red": self.hq_red,
            "hq_blue": self.hq_blue,
        }
        for nid, ndata in self.graph.nodes(data=True):
            pos = ndata.get("pos", (0, 0))
            data["nodes"][nid] = {
                "x": pos[0], "y": pos[1],
                "terrain": ndata.get("terrain", "normal"),
            }
        with open("maps/custom_map.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("地图已保存到 custom_map.json")

    def _load_map(self) -> None:
        """从 JSON 加载地图。"""
        try:
            with open("maps/custom_map.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            self._load_map_data(data)
            logger.info("地图已从 custom_map.json 加载")
        except FileNotFoundError:
            logger.warning("未找到 custom_map.json")

    def _evaluate_map(self) -> None:
        """评估当前地图公平性。"""
        if self.hq_red is None or self.hq_blue is None:
            logger.warning("请先设置 HQ")
            return
        evaluator = MapEvaluator(self.graph, self.hq_red, self.hq_blue)
        self.evaluation = evaluator.evaluate()

    def _draw(self) -> None:
        """绘制编辑器界面。"""
        self.screen.fill(BG_COLOR)

        # 绘制边
        for u, v in self.graph.edges():
            pos_u = self.graph.nodes[u].get("pos", (0, 0))
            pos_v = self.graph.nodes[v].get("pos", (0, 0))
            pygame.draw.line(self.screen, (150, 150, 150), pos_u, pos_v, 2)

        # 绘制连线虚线预览
        if self.is_drawing_line and self.line_start_nid is not None:
            if self.line_start_nid in self.graph.nodes:
                start_data = self.graph.nodes[self.line_start_nid]
                sx, sy = start_data.get("pos", (0, 0))
                mx, my = pygame.mouse.get_pos()
                dx, dy = mx - sx, my - sy
                length = math.hypot(dx, dy)
                if length >= 1:
                    step = 8
                    seg_count = max(1, int(length / step))
                    for i in range(0, seg_count, 2):
                        t1 = i / seg_count
                        t2 = min((i + 1) / seg_count, 1.0)
                        p1 = (int(sx + dx * t1), int(sy + dy * t1))
                        p2 = (int(sx + dx * t2), int(sy + dy * t2))
                        pygame.draw.line(self.screen, (255, 255, 255), p1, p2, 2)

        # 绘制节点
        for nid, data in self.graph.nodes(data=True):
            pos = data.get("pos", (0, 0))
            terrain = data.get("terrain", "normal")
            color = TERRAIN_COLOR.get(terrain, (200, 200, 200))

            # HQ 标记
            is_hq = nid in (self.hq_red, self.hq_blue)
            half = (TILE_SQUARE_SIZE // 2) + (4 if is_hq else 0)
            nx, ny = int(pos[0]), int(pos[1])
            tile_rect = pygame.Rect(nx - half, ny - half, half * 2, half * 2)

            pygame.draw.rect(self.screen, color, tile_rect,
                             border_radius=TILE_ROUND_RADIUS)
            if nid == self.selected_node:
                pygame.draw.rect(self.screen, (255, 255, 0),
                                 tile_rect.inflate(6, 6), 3,
                                 border_radius=TILE_ROUND_RADIUS + 3)

            # 地形符号
            sym = TERRAIN_SYM.get(terrain, "")
            if sym:
                text = self.font.render(sym, True, (0, 0, 0))
                self.screen.blit(text, (pos[0] - text.get_width() // 2, pos[1] - text.get_height() // 2))

        # 悬停提示
        if self.hover_node is not None:
            data = self.graph.nodes[self.hover_node]
            terrain = data.get("terrain", "normal")
            pos = data.get("pos", (0, 0))
            info = f"节点{self.hover_node} | 地形:{terrain}"
            if self.hover_node == self.hq_red:
                info += " | 红HQ"
            elif self.hover_node == self.hq_blue:
                info += " | 蓝HQ"
            tooltip = self.font.render(info, True, (255, 255, 255))
            bg_rect = tooltip.get_rect(topleft=(pos[0] + 15, pos[1] - 10))
            bg_rect.inflate_ip(8, 4)
            pygame.draw.rect(self.screen, (40, 40, 40), bg_rect)
            self.screen.blit(tooltip, (pos[0] + 19, pos[1] - 8))

        # 工具栏
        pygame.draw.rect(self.screen, (60, 60, 60), (0, self.toolbar_y, SCREEN_WIDTH, 60))
        for btn in self.terrain_buttons:
            color = btn["color"]
            if btn["terrain"] == self.selected_terrain:
                pygame.draw.rect(self.screen, (255, 255, 0), btn["rect"].inflate(4, 4), 3)
            pygame.draw.rect(self.screen, color, btn["rect"])
            label = self.font.render(btn["terrain"][:4], True, (0, 0, 0))
            self.screen.blit(label, (btn["rect"].x + 5, btn["rect"].y + 10))

        # 评估分数
        if self.evaluation:
            score_text = f"公平性: {self.evaluation.get('total', 0)}"
            text = self.font_large.render(score_text, True, (0, 255, 0) if self.evaluation.get("total", 0) >= 60 else (255, 100, 100))
            self.screen.blit(text, (SCREEN_WIDTH - 200, 10))

        # 快捷键提示
        hints = "Ctrl+N:新地图 | Ctrl+S:保存 | Ctrl+L:加载 | E:评估 | Ctrl+Z:撤销 | Ctrl+Shift+Z:重做"
        hint_text = self.font.render(hints, True, (180, 180, 180))
        self.screen.blit(hint_text, (10, 10))

        pygame.display.flip()


if __name__ == "__main__":
    editor = MapEditor()
    editor.run()