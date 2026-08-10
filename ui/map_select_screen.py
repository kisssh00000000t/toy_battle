"""
地图选择界面。

提供：随机地图开关、地图源切换（人工设计↔AI自动生成）、地图列表浏览（含评分）、
预览缩略图、开始游戏按钮、批量生成按钮。
"""

import logging
from pathlib import Path

import pygame

from .ui_const import ROAD_COLOR
from .base_screen import BaseScreen, play_stagger_spawn
from .widgets import (
    ToyButton, ToyLabel, ToyToggle, ToyPanel, TOY_COLORS,
    get_font, get_border_color,
)
from game.constants import TERRAIN_DATA, TERRAIN_KEY_ALIASES, NODE_RENDER_RADIUS, TILE_ROUND_RADIUS

logger = logging.getLogger(__name__)

# 地图目录（优先使用手动设计的地图）
_MAP_DIR = Path(__file__).parent.parent / "maps"
# 备用地图目录（评估筛选后的地图）
_FALLBACK_DIR = Path(__file__).parent.parent / "mapgen" / "out_maps"


class MapSelectScreen(BaseScreen):
    """地图选择界面。"""

    def __init__(self, manager, game_mode="local", net_client=None, is_host=True):
        super().__init__(manager)
        # 对战模式（从 ModeSelectModal 传入）
        self.game_mode = game_mode
        # 联网参数（从 NetLobbyScreen 传入）
        self.net_client = net_client
        self.is_host = is_host
        # 标题
        self.title = ToyLabel(
            "选择地图", (500, 30), font_size=48, color=TOY_COLORS["accent_coral"]
        )
        # 随机地图开关
        self.use_random = False
        self.toggle_random = ToyToggle(
            "随机地图", pos=(460, 100), callback=self._on_toggle_random, default=False
        )
        # 地图源切换：manual=人工设计, auto=AI自动生成
        self.current_source_type = "manual"
        self.btn_switch_source = ToyButton(
            "地图源: 人工设计", rect=(60, 100, 220, 40), callback=self._toggle_map_source,
            color=TOY_COLORS["soft_purple"], icon_type="edit"
        )
        # 地图列表区域（左侧，缩窄为预览腾出空间）
        self.map_panel = ToyPanel(rect=(60, 150, 680, 500))
        # 预览区域（右侧）
        self.preview_rect = pygame.Rect(760, 150, 460, 500)
        self.preview_surface = None
        self._prev_selected_idx = -2  # 用于检测选择变化，-2确保首次触发

        # 地图文件列表与评分
        self.map_files: list[Path] = []
        self.map_scores: dict[str, float] = {}  # {filename: score}
        self.selected_idx: int = -1
        self.scroll_offset = 0
        self._scan_maps()
        # 按钮
        self.btn_start = ToyButton(
            "开始游戏", rect=(460, 680, 360, 70), callback=self._start_game,
            color=TOY_COLORS["success_green"], icon_type="play"
        )
        self.btn_back = ToyButton(
            "返回", rect=(60, 680, 160, 50), callback=self._go_back,
            color=TOY_COLORS["danger_red"], icon_type="back"
        )
        self.btn_refresh = ToyButton(
            "刷新列表", rect=(1040, 680, 160, 50), callback=self._refresh,
            color=TOY_COLORS["soft_blue"], icon_type="refresh"
        )
        self.btn_generate = ToyButton(
            "批量生成", rect=(860, 680, 160, 50), callback=self._batch_generate,
            color=TOY_COLORS["warm_orange"], icon_type="add"
        )
        # 提示信息
        self.msg = ""
        self.msg_timer = 0
        # 生成中状态
        self._generating = False
        self.widgets = [
            self.title, self.toggle_random, self.btn_switch_source, self.map_panel,
            self.btn_start, self.btn_back, self.btn_refresh, self.btn_generate,
        ]

        # 交错入场动画
        play_stagger_spawn(self, anim_dur=0.4, gap=0.1, overlap_ratio=0.4)

    # ─── 地图扫描与评分 ──────────────────────────────────────

    def _scan_maps(self):
        """扫描地图目录中的JSON文件，按地图源类型定向扫描。"""
        self.map_files = []
        self.map_scores = {}
        if self.current_source_type == "manual":
            # 人工设计模式：优先 maps，备用 out_maps
            if _MAP_DIR.exists():
                self.map_files = sorted(_MAP_DIR.glob("map_*.json"))
            if not self.map_files and _FALLBACK_DIR.exists():
                self.map_files = sorted(_FALLBACK_DIR.glob("map_*.json"))
        else:
            # AI自动生成模式：优先 out_maps，备用 maps
            if _FALLBACK_DIR.exists():
                self.map_files = sorted(_FALLBACK_DIR.glob("map_*.json"))
            if not self.map_files and _MAP_DIR.exists():
                self.map_files = sorted(_MAP_DIR.glob("map_*.json"))
        # 尝试加载评分缓存
        self._load_scores()
        if not self.map_files:
            self.msg = "无地图文件，请使用随机模式或点击批量生成"
            self.msg_timer = 180

    def _load_scores(self):
        """尝试从CSV评估报告加载评分。"""
        import csv
        csv_path = _MAP_DIR / "map_evaluation_report.csv"
        if not csv_path.exists():
            csv_path = _FALLBACK_DIR / "map_evaluation_report.csv"
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        fname = f"map_{int(row['map_id']):02d}.json"
                        self.map_scores[fname] = float(row.get("total", 0))
            except (KeyError, ValueError, IOError):
                pass

    def _evaluate_current_maps(self):
        """评估当前地图目录中所有地图的评分。"""
        from mapgen import evaluate_batch
        if _MAP_DIR.exists() and list(_MAP_DIR.glob("map_*.json")):
            results = evaluate_batch(_MAP_DIR)
        elif _FALLBACK_DIR.exists():
            results = evaluate_batch(_FALLBACK_DIR)
        else:
            return
        for fname, score in results:
            self.map_scores[fname] = score

    # ─── 回调 ────────────────────────────────────────────────

    def _on_toggle_random(self, state):
        """随机地图开关回调。"""
        self.use_random = state

    def _toggle_map_source(self):
        """切换地图源：人工设计 ↔ AI自动生成。"""
        if self.current_source_type == "manual":
            self.current_source_type = "auto"
            self.btn_switch_source.text = "地图源: AI生成"
            self.btn_switch_source.color = TOY_COLORS["warm_orange"]
        else:
            self.current_source_type = "manual"
            self.btn_switch_source.text = "地图源: 人工设计"
            self.btn_switch_source.color = TOY_COLORS["soft_purple"]
        # 切换后重新扫描和评估
        self._scan_maps()
        self._evaluate_current_maps()
        self.selected_idx = -1
        self._prev_selected_idx = -2
        self.msg = f"已切换到{'AI生成' if self.current_source_type == 'auto' else '人工设计'}地图"
        self.msg_timer = 120

    def _go_back(self):
        """返回主菜单。"""
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def _refresh(self):
        """刷新地图列表并评估。"""
        self._scan_maps()
        self._evaluate_current_maps()
        self.selected_idx = -1
        self._prev_selected_idx = -2  # 强制预览刷新
        self.msg = f"已刷新，找到 {len(self.map_files)} 张地图"
        self.msg_timer = 120

    def _batch_generate(self):
        """批量生成并筛选地图（AI自动生成模式使用纺锤型生成器）。"""
        if self._generating:
            return
        self._generating = True
        self.msg = "正在生成地图..."
        self.msg_timer = 300
        try:
            from mapgen import generate_and_filter
            saved = generate_and_filter(n=20, threshold=60.0, keep_max=12)
            # 更新评分缓存
            for fname, score, _ in saved:
                self.map_scores[fname] = score
            # 切换到AI生成源
            self.current_source_type = "auto"
            self.btn_switch_source.text = "地图源: AI生成"
            self.btn_switch_source.color = TOY_COLORS["warm_orange"]
            self._scan_maps()
            self.selected_idx = -1
            self._prev_selected_idx = -2
            self.msg = f"生成完成！{len(saved)} 张合格地图"
            self.msg_timer = 180
        except Exception as e:
            logger.error(f"批量生成失败: {e}")
            self.msg = f"生成失败: {e}"
            self.msg_timer = 180
        finally:
            self._generating = False

    def _start_game(self):
        """开始游戏，切换到游戏界面。"""
        from .game_screen import GameScreen
        if self.use_random:
            # 随机地图模式：透传 game_mode + 联网参数
            self.manager.switch_to(GameScreen, map_data=None, game_mode=self.game_mode,
                                   net_client=self.net_client, is_host=self.is_host)
        else:
            if self.selected_idx < 0 or self.selected_idx >= len(self.map_files):
                self.msg = "请先选择一张地图或开启随机模式"
                self.msg_timer = 120
                return
            from game.map_loader import MapLoader
            map_data = MapLoader.load_json(self.map_files[self.selected_idx])
            # 选定地图模式：透传 game_mode + 联网参数
            self.manager.switch_to(GameScreen, map_data=map_data, game_mode=self.game_mode,
                                   net_client=self.net_client, is_host=self.is_host)

        # 联网主机：开局后发送 sync_game_start 给客机，确保双端牌堆/手牌一致
        if self.game_mode == "net" and self.is_host and self.net_client:
            # 获取刚创建的 GameScreen 实例
            gs = self.manager.current_screen
            if gs and hasattr(gs, 'game'):
                self.net_client.send_action({
                    "act_type": "sync_game_start",
                    "map_data": gs.game.board.to_dict() if hasattr(gs.game.board, 'to_dict') else None,
                    "game_state": gs.game.to_dict(),
                })

    # ─── 预览缩略图生成 ─────────────────────────────────────

    def _generate_preview(self, map_data: dict) -> pygame.Surface:
        """根据地图数据生成预览缩略图 Surface。

        绘制：道路(单线) + 地形节点(圆+边框+符号) + 区块星星(灰色\u2606) + HQ标记。
        """
        # 预览内容区域尺寸（与 draw 中 preview_content_rect 一致）
        pw = self.preview_rect.width - 8
        ph = self.preview_rect.height - 32
        surf = pygame.Surface((pw, ph))
        surf.fill(TOY_COLORS["bg_cream"])

        nodes = map_data.get("nodes", [])
        edges = map_data.get("edges", [])
        area_centers = map_data.get("area_centers", {})

        if not nodes:
            font = get_font(20, style="chinese")
            txt = font.render("无有效地图数据", True, TOY_COLORS["dark_text"])
            surf.blit(txt, (pw // 2 - txt.get_width() // 2,
                           ph // 2 - txt.get_height() // 2))
            return surf

        # --- 1. 计算包围盒 ---
        NODE_R = NODE_RENDER_RADIUS + 6  # 含边框的视觉半径
        min_x = min(nd["x"] for nd in nodes)
        max_x = max(nd["x"] for nd in nodes)
        min_y = min(nd["y"] for nd in nodes)
        max_y = max(nd["y"] for nd in nodes)
        map_w = max_x - min_x + 2 * NODE_R
        map_h = max_y - min_y + 2 * NODE_R

        # --- 2. 等比缩放 + 居中 ---
        margin = 20
        scale_x = (pw - 2 * margin) / map_w if map_w > 0 else 1
        scale_y = (ph - 2 * margin) / map_h if map_h > 0 else 1
        scale = min(scale_x, scale_y)
        offset_x = (pw - map_w * scale) / 2 - (min_x - NODE_R) * scale
        offset_y = (ph - map_h * scale) / 2 - (min_y - NODE_R) * scale

        def w2s(wx, wy):
            """世界坐标 → 预览 Surface 坐标。"""
            return int(wx * scale + offset_x), int(wy * scale + offset_y)

        # --- 3. 节点字典（按 nid 索引）---
        node_dict = {nd["nid"]: nd for nd in nodes}

        # --- 4. 绘制道路（单线，浅沙色）---
        road_color = ROAD_COLOR
        for e in edges:
            u_id, v_id = e["u"], e["v"]
            if u_id in node_dict and v_id in node_dict:
                p1 = w2s(node_dict[u_id]["x"], node_dict[u_id]["y"])
                p2 = w2s(node_dict[v_id]["x"], node_dict[v_id]["y"])
                line_w = max(1, int(2 * scale))
                pygame.draw.line(surf, road_color, p1, p2, line_w)

        # --- 5. 绘制地形节点 ---
        for nd in nodes:
            sx, sy = w2s(nd["x"], nd["y"])
            r = max(3, int(NODE_RENDER_RADIUS * scale))
            terrain_key = nd.get("terrain", "normal")
            terrain_key = TERRAIN_KEY_ALIASES.get(terrain_key, terrain_key)
            ter = TERRAIN_DATA.get(terrain_key, TERRAIN_DATA["normal"])
            # 填充（圆角方形）
            fill_color = ter["color"]
            tile_rect = pygame.Rect(sx - r, sy - r, r * 2, r * 2)
            pygame.draw.rect(surf, fill_color, tile_rect,
                             border_radius=TILE_ROUND_RADIUS)
            # 边框（对撞色）
            border_color = ter.get("border_color", get_border_color(terrain_key))
            border_w = max(1, int(3 * scale))
            pygame.draw.rect(surf, border_color, tile_rect, border_w,
                             border_radius=TILE_ROUND_RADIUS)
            # HQ 金色外框
            if nd.get("is_hq"):
                hq_ring_w = max(2, int(4 * scale))
                hq_color = (255, 200, 50) if nd.get("hq_owner") == "red" else (100, 150, 255)
                pygame.draw.rect(surf, hq_color,
                                 tile_rect.inflate(hq_ring_w * 2, hq_ring_w * 2),
                                 hq_ring_w, border_radius=TILE_ROUND_RADIUS + hq_ring_w)
            # 中心名称缩写（替代emoji符号）
            if r > 8:
                ter_name = ter.get("name", "")
                if ter_name:
                    sym_size = max(10, int(14 * scale))
                    sym_font = get_font(sym_size, style="chinese")
                    sym_surf = sym_font.render(ter_name[:2], True, TOY_COLORS["dark_text"])
                    surf.blit(sym_surf, (sx - sym_surf.get_width() // 2,
                                         sy - sym_surf.get_height() // 2))

        # --- 6. 绘制区块星星（缓存blit）---
        if area_centers:
            from .render_cache import get_cached_star
            star_size = max(6, int(10 * scale))
            for aid, center in area_centers.items():
                if isinstance(center, (list, tuple)) and len(center) >= 2:
                    cx, cy = center[0], center[1]
                else:
                    continue
                sx, sy = w2s(cx, cy)
                star_surf = get_cached_star("gray", star_size)
                surf.blit(star_surf, (int(sx) - star_surf.get_width() // 2,
                                       int(sy) - star_surf.get_height() // 2))

        return surf

    def _update_preview(self):
        """当选择变化时重建预览 Surface。"""
        if self.selected_idx == self._prev_selected_idx:
            return  # 未变化，跳过
        self._prev_selected_idx = self.selected_idx
        if 0 <= self.selected_idx < len(self.map_files):
            try:
                from game.map_loader import MapLoader
                map_data = MapLoader.load_json(self.map_files[self.selected_idx])
                self.preview_surface = self._generate_preview(map_data)
            except Exception as e:
                logger.warning(f"预览生成失败: {e}")
                self.preview_surface = None
        else:
            self.preview_surface = None

    # ─── 事件与更新 ──────────────────────────────────────────

    def handle_event(self, event):
        """处理事件，包含地图列表点击。"""
        super().handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            # 检查地图列表点击
            if self.map_panel.rect.collidepoint(mx, my):
                item_y = self.map_panel.rect.y + 10 - self.scroll_offset
                for i, mf in enumerate(self.map_files):
                    item_rect = pygame.Rect(
                        self.map_panel.rect.x + 10, item_y,
                        self.map_panel.rect.width - 20, 36
                    )
                    if item_rect.collidepoint(mx, my):
                        self.selected_idx = i
                        break
                    item_y += 42
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll_offset = max(0, self.scroll_offset - event.y * 30)

    def update(self, dt):
        if self.msg_timer > 0:
            self.msg_timer -= 1
        # 检测选择变化，更新预览
        self._update_preview()

    # ─── 绘制 ────────────────────────────────────────────────

    def draw(self, surface):
        super().draw(surface)

        # ── 左侧：地图列表 ──
        font = get_font(20, style="chinese")
        score_font = get_font(16, style="chinese")
        if not self.map_files:
            txt = font.render("无地图文件，请使用随机模式或先批量生成", True, TOY_COLORS["dark_text"])
            surface.blit(txt, (80, 170))
        else:
            clip_rect = self.map_panel.rect
            surface.set_clip(clip_rect)
            item_y = clip_rect.y + 10 - self.scroll_offset
            for i, mf in enumerate(self.map_files):
                item_rect = pygame.Rect(clip_rect.x + 10, item_y, clip_rect.width - 20, 36)
                # 选中高亮
                if i == self.selected_idx:
                    pygame.draw.rect(surface, TOY_COLORS["primary_yellow"], item_rect, border_radius=8)
                else:
                    bg = TOY_COLORS["panel_bg"] if i % 2 == 0 else (245, 243, 235)
                    pygame.draw.rect(surface, bg, item_rect, border_radius=4)
                # 文字
                name_txt = font.render(mf.name, True, TOY_COLORS["dark_text"])
                surface.blit(name_txt, (item_rect.x + 12, item_rect.y + 6))
                # 评分
                score = self.map_scores.get(mf.name)
                if score is not None:
                    if score >= 70:
                        sc = TOY_COLORS["success_green"]
                    elif score >= 50:
                        sc = TOY_COLORS["primary_yellow"]
                    else:
                        sc = TOY_COLORS["danger_red"]
                    score_txt = score_font.render(f"评分: {score:.1f}", True, sc)
                    surface.blit(score_txt, (item_rect.right - 120, item_rect.y + 8))
                item_y += 42
            surface.set_clip(None)

        # ── 右侧：预览区域 ──
        # 预览框背景
        pygame.draw.rect(surface, TOY_COLORS["panel_bg"], self.preview_rect, border_radius=12)
        pygame.draw.rect(surface, TOY_COLORS["panel_stroke"], self.preview_rect, 2, border_radius=12)
        # 预览标题
        preview_title_font = get_font(16, style="chinese")
        preview_title = preview_title_font.render("地图预览", True, TOY_COLORS["dark_text"])
        surface.blit(preview_title, (self.preview_rect.centerx - preview_title.get_width() // 2,
                                     self.preview_rect.y + 6))
        # 预览内容
        preview_content_rect = pygame.Rect(
            self.preview_rect.x + 4, self.preview_rect.y + 28,
            self.preview_rect.width - 8, self.preview_rect.height - 32
        )
        if self.preview_surface:
            surface.blit(self.preview_surface, preview_content_rect.topleft)
        else:
            hint_font = get_font(22, style="chinese")
            hint = hint_font.render("点击左侧地图查看预览", True, (180, 170, 160))
            surface.blit(hint, (preview_content_rect.centerx - hint.get_width() // 2,
                                preview_content_rect.centery - hint.get_height() // 2))

        # ── 底部提示信息 ──
        if self.msg_timer > 0 and self.msg:
            msg_font = get_font(18, style="chinese")
            msg_surf = msg_font.render(self.msg, True, TOY_COLORS["success_green"])
            surface.blit(msg_surf, (460, 750))