"""
创意工坊二级界面 — 地图编辑、批量产出与评估打分。

独立 Screen 场景，通过 manager.switch_to 切换，
物理层面与主菜单完全隔离，杜绝事件穿透。
"""

import json
import logging
from pathlib import Path

import pygame

from .base_screen import BaseScreen, play_stagger_spawn
from .widgets import ToyButton, ToyLabel, ToyPanel, ToyTitle, TOY_COLORS, get_font

logger = logging.getLogger(__name__)


class WorkshopScreen(BaseScreen):
    """二级界面：创意工坊 (Workshop) — 地图编辑、批量产出与评估打分"""

    def __init__(self, manager):
        super().__init__(manager)

        # 1. 顶部标题
        self.title = ToyTitle(
            "创意工坊", center_x=manager.WIN_W // 2, center_y=100,
            font_size=64, base_color=TOY_COLORS["secondary_cyan"]
        )
        self.subtitle = ToyLabel(
            "Workshop & Map Tools", (manager.WIN_W // 2 - 110, 160),
            font_size=24, color=TOY_COLORS["dark_text"]
        )

        # 2. 中央功能底框
        pw, ph = 640, 420
        px, py = (manager.WIN_W - pw) // 2, 200
        self.panel = ToyPanel((px, py, pw, ph))

        # 3. 核心大按钮
        bx = px + 80
        self.btn_editor = ToyButton(
            "进入地图编辑器", rect=(bx, py + 50, 480, 66),
            callback=self._goto_editor,
            color=TOY_COLORS["primary_yellow"], icon_type="edit"
        )
        self.btn_batch_gen = ToyButton(
            "批量生成地图 (12张)", rect=(bx, py + 140, 480, 66),
            callback=self._do_batch_generate,
            color=TOY_COLORS["soft_blue"], icon_type="add"
        )
        self.btn_eval_all = ToyButton(
            "地图公平评估打分", rect=(bx, py + 230, 480, 66),
            callback=self._do_evaluate_all,
            color=TOY_COLORS["accent_coral"], icon_type="chart"
        )
        self.btn_back = ToyButton(
            "返回主菜单", rect=(bx + 140, py + 320, 200, 52),
            callback=self._go_back,
            color=TOY_COLORS["danger_red"], icon_type="back"
        )

        # 4. 底部反馈提示
        self.status_msg = ""
        self.status_timer = 0
        self.msg_color = TOY_COLORS["success_green"]

        self.widgets = [
            self.title, self.subtitle,
            self.btn_editor, self.btn_batch_gen, self.btn_eval_all, self.btn_back
        ]

        # 进场交互动画
        play_stagger_spawn(self, anim_dur=0.35, gap=0.08, overlap_ratio=0.3)

    # ─── 回调 ────────────────────────────────────────────────

    def _goto_editor(self):
        from .editor_screen import EditorScreen
        self.manager.switch_to(EditorScreen)

    def _go_back(self):
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def _do_batch_generate(self):
        """调用 MapGenerator 批量生成 12 张合法随机地图"""
        try:
            from mapgen.map_generator import MapGenerator
            out_dir = Path(__file__).parent.parent / "mapgen" / "out_maps"
            out_dir.mkdir(parents=True, exist_ok=True)
            count = 0
            for i in range(12):
                gen = MapGenerator(cols=7, rows=5)
                data = gen.generate()
                path = out_dir / f"map_{i + 1:02d}.json"
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                count += 1
            self._show_msg(f"\u2713 成功生成 {count} 张随机地图至 mapgen/out_maps/")
        except Exception as e:
            logger.error(f"批量生成地图失败: {e}")
            self._show_msg(f"生成出错: {e}", error=True)

    def _do_evaluate_all(self):
        """读取地图并调用 MapEvaluator 自动打分"""
        try:
            from mapgen.map_evaluator import MapEvaluator
            from game.map_loader import MapLoader
            out_dir = Path(__file__).parent.parent / "mapgen" / "out_maps"
            json_files = sorted(out_dir.glob("map_*.json"))
            if not json_files:
                self._show_msg("目录 mapgen/out_maps/ 为空，请先点击「批量生成」！", error=True)
                return

            results = []
            for jf in json_files:
                data = MapLoader.load_json(jf)
                import networkx as nx
                G = nx.Graph()
                for nd in data.get("nodes", []):
                    G.add_node(nd["nid"], pos=(nd["x"], nd["y"]),
                               terrain=nd.get("terrain", "normal"))
                for e in data.get("edges", []):
                    G.add_edge(e["u"], e["v"])
                hq_r, hq_b = data.get("hq_red"), data.get("hq_blue")
                if hq_r is not None and hq_b is not None:
                    ev = MapEvaluator(G, hq_r, hq_b)
                    score = ev.evaluate().get("total", 0)
                    results.append((jf.name, score))

            if results:
                best = max(results, key=lambda x: x[1])
                self._show_msg(f"评估完成 ({len(results)}张) | 最优: {best[0]} ({best[1]:.1f}分)")
            else:
                self._show_msg("地图缺少 HQ 总部坐标，无法评估", error=True)
        except Exception as e:
            logger.error(f"评估异常: {e}")
            self._show_msg(f"评估出错: {e}", error=True)

    def _show_msg(self, msg: str, error: bool = False):
        self.status_msg = msg
        self.status_timer = 240
        self.msg_color = TOY_COLORS["danger_red"] if error else TOY_COLORS["success_green"]

    # ─── 更新与绘制 ──────────────────────────────────────────

    def update(self, dt):
        if self.status_timer > 0:
            self.status_timer -= 1
        self.title.update(dt)

    def handle_event(self, event):
        super().handle_event(event)
        self.title.handle_event(event)

    def draw(self, surface):
        surface.fill(TOY_COLORS["bg_cream"])
        self.panel.draw(surface)
        self.title.draw(surface)
        for w in self.widgets:
            w.draw(surface)
        if self.status_timer > 0 and self.status_msg:
            font = get_font(20, bold=True, style="chinese")
            s_surf = font.render(self.status_msg, True, self.msg_color)
            surface.blit(s_surf, ((self.manager.WIN_W - s_surf.get_width()) // 2, 660))