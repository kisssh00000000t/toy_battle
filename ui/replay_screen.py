"""
战报回放观战界面 — 7层地图渲染 + 执子时决。

独立 Screen 场景，加载 JSON 战报文件，逐步执行 action_log，
实时渲染棋盘地图、节点控制权、驻军棋子、双方积分、落子音效。
"""

import json
import logging
import math
from pathlib import Path

import pygame

from .base_screen import BaseScreen, play_stagger_spawn
from .widgets import (
    ToyButton, ToyLabel, ToyPanel, ToyTitle, TOY_COLORS,
    get_font, draw_rounded_rect, darken_color,
)
from .camera import Camera
from .render_cache import get_cached_troop, get_cached_terrain, get_cached_star
from .ui_const import (
    BG_CREAM, ROAD_COLOR, AREA_BOUNDS_COLORS, TEXT_MUTED,
    GRID_TILE_SIZE, GRID_LINE_COLOR, GRID_LINE_WIDTH,
    FACTION_BG_ALPHA, CAMERA_FIT_PADDING,
    BORDER_WHITE, FALLBACK_GRAY,
)
from .ui_utils import make_grid_tile, tile_blit_grid, draw_alpha_rect
from game.constants import (
    TERRAIN_COLOR, PLAYER_COLORS, NODE_RENDER_RADIUS,
    TILE_ROUND_RADIUS, TILE_PADDING, TEAM_BG_ALPHA,
)
from game.sound import play as play_sound, SND_CLICK, SND_PLACE, SND_DRAW, SND_TURN, SND_WIN

logger = logging.getLogger(__name__)


class ReplayScreen(BaseScreen):
    """战报回放观战界面 — 7层地图渲染 + 执子时决。"""

    def __init__(self, manager, replay_file: Path = None,
                 action_log: list = None, map_source: str = "custom"):
        super().__init__(manager)

        self.replay_file = replay_file
        self.map_source = map_source
        self.replay_data = {}
        self.action_log: list[dict] = action_log or []
        self.current_step = 0
        self.auto_playing = False
        self.auto_timer = 0.0
        self.auto_interval = 0.8

        # ── 核心修复：必须先实例化 Camera 和底图缓存，绝不可置后 ──
        self.camera = Camera(manager.WIN_W, manager.WIN_H)
        self.bg_cache = None
        self.bg_dirty = True
        self._grid_tile_surf = make_grid_tile(GRID_TILE_SIZE, GRID_LINE_COLOR, GRID_LINE_WIDTH)

        # ── 加载并重建初始棋盘 ──
        self.game = None
        if action_log is not None:
            self._rebuild_game_from_action_log()
        else:
            self._load_replay()

        # ── 顶部与局势文字标签 ──
        self.title = ToyTitle(
            "对弈战报观战", center_x=manager.WIN_W // 2, center_y=45,
            font_size=42, base_color=TOY_COLORS["secondary_cyan"]
        )
        self.step_label = ToyLabel(
            self._step_text(), (20, 20), font_size=20, color=TOY_COLORS["dark_text"]
        )
        self.status_msg = "点击底部的 [下一步] 或 [自动播放] 观赏对弈"
        self.status_timer = 180

        # ── 底部控制条底框 ──
        self.control_panel_rect = pygame.Rect(40, manager.WIN_H - 96, manager.WIN_W - 80, 76)

        btn_y = manager.WIN_H - 82
        self.btn_step = ToyButton(
            "下一步 \u25B6", rect=(manager.WIN_W // 2 - 180, btn_y, 160, 48),
            callback=self._step_forward,
            color=TOY_COLORS["primary_yellow"], icon_type="play"
        )
        self.btn_auto = ToyButton(
            "\U0001F916 自动播放", rect=(manager.WIN_W // 2, btn_y, 180, 48),
            callback=self._toggle_auto,
            color=TOY_COLORS["soft_blue"], icon_type="refresh"
        )
        self.btn_reset = ToyButton(
            "\U0001F504 开局", rect=(manager.WIN_W // 2 + 200, btn_y, 120, 48),
            callback=self._reset_replay,
            color=TOY_COLORS["soft_purple"], icon_type="back"
        )
        self.btn_back = ToyButton(
            "返回大厅", rect=(60, btn_y, 140, 48),
            callback=self._go_back,
            color=TOY_COLORS["danger_red"], icon_type="back"
        )

        self.widgets = [self.title, self.step_label, self.btn_step, self.btn_auto, self.btn_reset, self.btn_back]
        play_stagger_spawn(self, anim_dur=0.3, gap=0.06, overlap_ratio=0.3)

    def calc_map_transform(self):
        """自动调整相机缩放与视野，避开顶部横幅与底部控制条。"""
        if not self.game or not self.game.board.nodes:
            return
        board = self.game.board
        pad = NODE_RENDER_RADIUS + 8
        min_x = min(nd.x - pad for nd in board.nodes.values())
        min_y = min(nd.y - pad for nd in board.nodes.values())
        max_x = max(nd.x + pad for nd in board.nodes.values())
        max_y = max(nd.y + pad for nd in board.nodes.values())

        view_rect = (20, 80, self.manager.WIN_W - 40, self.manager.WIN_H - 200)
        self.camera.fit_to_world(
            world_bounds=(min_x, min_y, max_x, max_y),
            view_rect=view_rect,
            padding_ratio=CAMERA_FIT_PADDING,
        )

    def _load_replay(self):
        if self.replay_file is None or not self.replay_file.exists():
            return
        try:
            with open(self.replay_file, "r", encoding="utf-8") as f:
                self.replay_data = json.load(f)
            self.action_log = self.replay_data.get("action_log", [])
            self._rebuild_game()
        except Exception as e:
            logger.error(f"读取录像异常: {e}")

    def _rebuild_game_from_action_log(self):
        try:
            from game.game_logic import GameState
            from game.map_loader import load_map, MapLoader
            from game.troop import Troop
            self.game = GameState()

            # ── 1. 优先从已固化的 map_data 恢复对齐主战场 ──
            if "map_data" in self.replay_data and self.replay_data["map_data"]:
                self.game.board.load_from_dict(self.replay_data["map_data"])
            else:
                # 兼容老版路径逻辑
                map_src = self.replay_data.get("map_source", self.map_source)
                loaded = False
                if map_src and str(map_src) not in ("random", "custom", "custom_map"):
                    try:
                        mp = Path(map_src)
                        if mp.exists():
                            mdata = MapLoader.load_json(mp)
                            self.game.board.load_from_dict(mdata)
                            loaded = True
                    except Exception:
                        pass
                if not loaded:
                    random_map = load_map()
                    self.game.board.load_from_dict(random_map)

            # ── 2. 确定性初始化：使用 initial_decks + first_player ──
            initial_decks = self.replay_data.get("initial_decks")
            first_player = self.replay_data.get("first_player")
            if initial_decks and first_player:
                for color in ("red", "blue"):
                    player = self.game.red if color == "red" else self.game.blue
                    keys = initial_decks.get(color, [])
                    player.reserve = [Troop(k, color) for k in keys]
                self.game.current_player_color = first_player
                self.game.first_player = first_player
                self.game.initial_decks = initial_decks
                if first_player == "red":
                    self.game.red.init_draw(True)
                    self.game.blue.init_draw(False)
                else:
                    self.game.blue.init_draw(True)
                    self.game.red.init_draw(False)
            else:
                self.game.setup()

            self.game.action_log = []
            self.current_step = 0
            self.calc_map_transform()
            self.bg_dirty = True
        except Exception as e:
            logger.error(f"从 action_log 重启对局发生异常: {e}")
            self.game = None

    def _rebuild_game(self):
        try:
            from game.game_logic import GameState
            from game.map_loader import load_map, MapLoader
            from game.troop import Troop
            self.game = GameState()

            # ── 1. 优先提取 JSON 中的 map_data 快照 ──
            if "map_data" in self.replay_data and self.replay_data["map_data"]:
                self.game.board.load_from_dict(self.replay_data["map_data"])
            else:
                # 2. 兼容老版本无 map_data 的战报：尝试从路径或者默认图加载
                map_src = self.replay_data.get("map_source", self.map_source)
                loaded = False
                if map_src and str(map_src) not in ("random", "custom", "custom_map"):
                    try:
                        mp = Path(map_src)
                        if mp.exists():
                            mdata = MapLoader.load_json(mp)
                            self.game.board.load_from_dict(mdata)
                            loaded = True
                    except Exception as e:
                        logger.warning(f"指定地图 {map_src} 读取失败，回退随机地图: {e}")
                if not loaded:
                    random_map = load_map()
                    self.game.board.load_from_dict(random_map)

            # ── 3. 确定性初始化：使用 initial_decks + first_player ──
            initial_decks = self.replay_data.get("initial_decks")
            first_player = self.replay_data.get("first_player")
            if initial_decks and first_player:
                # 确定性模式：按记录的牌堆顺序重建 reserve
                for color in ("red", "blue"):
                    player = self.game.red if color == "red" else self.game.blue
                    keys = initial_decks.get(color, [])
                    player.reserve = [Troop(k, color) for k in keys]
                self.game.current_player_color = first_player
                self.game.first_player = first_player
                self.game.initial_decks = initial_decks
                # 先手抽3、后手抽4
                if first_player == "red":
                    self.game.red.init_draw(True)
                    self.game.blue.init_draw(False)
                else:
                    self.game.blue.init_draw(True)
                    self.game.red.init_draw(False)
            else:
                # 兼容旧版战报：回退到随机 setup
                self.game.setup()

            self.game.action_log = []
            self.current_step = 0
            # 重建完毕立即适配相机视野与背景
            self.calc_map_transform()
            self.bg_dirty = True
        except Exception as e:
            logger.error(f"重置对局环境异常: {e}")
            self.game = None

    def _apply_action(self, action: dict):
        """执行单条对弈记录，基于 troop_key 确定性匹配，杜绝模糊兜底。"""
        if self.game is None:
            return
        try:
            atype = action.get("type")
            player = action.get("player", "red")
            data = action.get("data", {})

            if atype == "draw":
                play_sound(SND_DRAW)
                self.game.draw_cards_action()
                self.status_msg = f"\u2713 [步骤 {self.current_step + 1}] {player.upper()} 方抽取卡牌"

            elif atype == "place":
                # 优先使用标准 troop_key（新格式），否则降级兼容旧战报的模糊字符串
                target_key = data.get("troop_key")
                target_nid = data.get("node") or data.get("node_id")

                if target_nid is not None:
                    cp = self.game.current_player
                    target_troop = None

                    # 1. 严格 troop_key 匹配（确定性回放）
                    if target_key is not None:
                        for t in cp.hand:
                            if t.troop_key == target_key:
                                target_troop = t
                                break
                    else:
                        # 2. 仅对旧版无 troop_key 的历史战报保留基础字符匹配
                        troop_info = str(data.get("troop", ""))
                        for t in cp.hand:
                            if (str(t.troop_key) in troop_info
                                    or t.alias in troop_info
                                    or t.name in troop_info
                                    or str(t) == troop_info):
                                target_troop = t
                                break

                    # ── 无损复原容错：动态为当前阵营实例化替补合法棋子 ──
                    # 【核心修复】：容错生成的战棋必须 append 进手牌！
                    # 否则 place_troop() 引擎校验"手牌无该兵种"会驳回，导致连锁连通性断裂
                    if not target_troop:
                        from game.troop import Troop
                        fallback_key = target_key if target_key is not None else 1
                        target_troop = Troop(fallback_key, cp.color)
                        # 关键：必须加入当前玩家手牌，否则引擎判定"手牌无该兵种"驳回！
                        cp.hand.append(target_troop)
                        logger.warning(
                            f"由于卡堆偏离，已为 [{player}] 自动纠偏并注入手牌战棋: {fallback_key}"
                        )

                    node = self.game.board.get_node(int(target_nid))
                    if target_troop and node:
                        ok = self.game.place_troop(target_troop, node)
                        if ok:
                            play_sound(SND_PLACE)
                            self.bg_dirty = True
                            self.status_msg = (
                                f"\u2713 [步骤 {self.current_step + 1}] "
                                f"{player.upper()} 方放置 [{target_troop.name}] 至 节点{node.nid}"
                            )
                            if self.game.game_over:
                                play_sound(SND_WIN)
                                self.status_msg = f"\U0001F3C6 决战结束！{self.game.winner.upper()} 赢得最后胜利！"
                            elif not self.game.extra_place_pending:
                                self.game.end_turn()
                                play_sound(SND_TURN)
                        else:
                            logger.error(
                                f"回放第 {self.current_step} 步规则驳回: {self.game.turn_msg}"
                            )
                            self.status_msg = f"\u26A0 步骤{self.current_step + 1} 放置被规则驳回"
                            self.auto_playing = False

            self.status_timer = 120
        except Exception as e:
            logger.error(f"战报步骤 {self.current_step} 发生同步中断: {e}", exc_info=True)
            self.status_msg = f"\u26A0 执行步骤 {self.current_step + 1} 时发生错误"
            self.auto_playing = False

    def _step_forward(self):
        if self.current_step < len(self.action_log):
            action = self.action_log[self.current_step]
            self._apply_action(action)
            self.current_step += 1
            self.step_label.text = self._step_text()
            self.step_label._font = None
        else:
            self.auto_playing = False
            self.btn_auto.text = "\U0001F916 自动播放"
            self.status_msg = "\u2713 所有对战步骤已播完！"
            self.status_timer = 180

    def _toggle_auto(self):
        self.auto_playing = not self.auto_playing
        self.auto_timer = 0.0
        self.btn_auto.text = "\u23F8 暂停对弈" if self.auto_playing else "\U0001F916 自动播放"
        play_sound(SND_CLICK)

    def _reset_replay(self):
        self._rebuild_game()
        self.current_step = 0
        self.auto_playing = False
        self.btn_auto.text = "\U0001F916 自动播放"
        self.step_label.text = self._step_text()
        self.step_label._font = None
        self.status_msg = "\U0001F504 对弈局面已重置回到开局时刻"
        self.status_timer = 120
        play_sound(SND_CLICK)

    def _go_back(self):
        from .replay_select_screen import ReplaySelectScreen
        self.manager.switch_to(ReplaySelectScreen)

    def _step_text(self) -> str:
        total = len(self.action_log)
        return f"当前步骤: {self.current_step} / {total}"

    def update(self, dt):
        self.title.update(dt)
        self.camera.update(dt)
        if self.camera.dirty:
            self.bg_dirty = True
            self.camera.dirty = False

        if self.status_timer > 0:
            self.status_timer -= 1

        if self.auto_playing and self.current_step < len(self.action_log):
            self.auto_timer += dt
            if self.auto_timer >= self.auto_interval:
                self.auto_timer = 0.0
                self._step_forward()

    def handle_event(self, event):
        super().handle_event(event)
        self.title.handle_event(event)
        self.camera.handle_event(event)
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RIGHT, pygame.K_SPACE):
                self._step_forward()
            elif event.key == pygame.K_ESCAPE:
                self._go_back()

    def draw(self, surface):
        try:
            surface.fill(TOY_COLORS["bg_cream"])
            self._draw_board(surface)
            self._draw_info_bar(surface)

            # 底部操作按钮面板
            draw_rounded_rect(
                surface, TOY_COLORS["panel_bg"], self.control_panel_rect,
                radius=16, stroke_width=2, stroke_color=TOY_COLORS["panel_stroke"]
            )

            for w in self.widgets:
                if hasattr(w, "draw"):
                    w.draw(surface)

            if self.status_timer > 0 and self.status_msg:
                font = get_font(18, bold=True, style="chinese")
                s_surf = font.render(self.status_msg, True, TOY_COLORS["dark_text"])
                surface.blit(s_surf, (self.manager.WIN_W // 2 - s_surf.get_width() // 2, self.manager.WIN_H - 128))
        except Exception as e:
            logger.warning(f"渲染时跳过异常区域，保障回放不断屏: {e}")

    def _draw_board(self, surface):
        """完全还原对战画面的 7 层协议渲染棋盘与驻军。"""
        if self.game is None or self.game.board is None:
            return
        if self.bg_dirty or self.bg_cache is None:
            self._rebuild_bg_cache()
        surface.blit(self.bg_cache, (0, 0))

        board = self.game.board
        t = self.camera
        nr = t.scaled_radius(NODE_RENDER_RADIUS)
        nr_hq = nr + max(1, int(4 * t.scale))

        # 1. 阵营占领底色
        for nid, node in board.nodes.items():
            if not node.top_troop:
                continue
            sx, sy = t.world_to_screen(node.x, node.y)
            half = nr_hq if node.is_hq else nr
            owner_color = PLAYER_COLORS.get(node.top_troop.owner, FALLBACK_GRAY)
            tile_rect = pygame.Rect(int(sx) - half, int(sy) - half, half * 2, half * 2)
            draw_alpha_rect(surface, (*owner_color, FACTION_BG_ALPHA), tile_rect, radius=TILE_ROUND_RADIUS)

        # 2. 地形贴图
        for nid, nd in board.nodes.items():
            sx, sy = t.world_to_screen(nd.x, nd.y)
            half = nr_hq if nd.is_hq else nr
            inner_half = half - int(TILE_PADDING * t.scale)
            ter_size = max(4, int(inner_half * 1.4))
            ter_surf = get_cached_terrain(nd.terrain_key, target_size=ter_size)
            surface.blit(ter_surf, (int(sx) - ter_surf.get_width() // 2, int(sy) - ter_surf.get_height() // 2))

        # 3. 星星比分标记
        for sp in board.star_points:
            if not sp.get("has_star", True):
                continue
            sx, sy = t.world_to_screen(sp["x"], sp["y"])
            aid = sp.get("area_id", -1)
            star_size = max(8, int(14 * t.scale * 0.65))
            if aid in self.game.red.captured_areas:
                star_surf = get_cached_star("red", star_size)
            elif aid in self.game.blue.captured_areas:
                star_surf = get_cached_star("blue", star_size)
            else:
                star_surf = get_cached_star("gray", star_size)
            trans_surf = star_surf.copy()
            trans_surf.set_alpha(190)
            surface.blit(trans_surf, (int(sx) - star_surf.get_width() // 2, int(sy) - star_surf.get_height() // 2))

        # 4. 真实士兵棋子显示
        for nid, node in board.nodes.items():
            if not node.top_troop:
                continue
            sx, sy = t.world_to_screen(node.x, node.y)
            half = nr_hq if node.is_hq else nr
            troop = node.top_troop
            owner_color = PLAYER_COLORS.get(troop.owner, FALLBACK_GRAY)
            base_half = half - max(2, int(8 * t.scale))
            base_rect = pygame.Rect(int(sx) - base_half, int(sy) - base_half, base_half * 2, base_half * 2)
            bg_surf = pygame.Surface((base_half * 2, base_half * 2), pygame.SRCALPHA)
            pygame.draw.rect(bg_surf, (*owner_color, TEAM_BG_ALPHA), bg_surf.get_rect(), border_radius=TILE_ROUND_RADIUS)
            surface.blit(bg_surf, base_rect.topleft)
            pygame.draw.rect(surface, BORDER_WHITE, base_rect, max(1, int(2 * t.scale)), border_radius=TILE_ROUND_RADIUS)
            tro_surf = get_cached_troop(troop.troop_key, troop.owner, target_size=int(base_half * 1.6))
            surface.blit(tro_surf, (int(sx) - tro_surf.get_width() // 2, int(sy) - tro_surf.get_height() // 2))

    def _rebuild_bg_cache(self):
        self.bg_cache = pygame.Surface((self.manager.WIN_W, self.manager.WIN_H))
        self.bg_cache.fill(BG_CREAM)
        tile_blit_grid(self.bg_cache, self._grid_tile_surf)
        # 绘制道路边线
        board = self.game.board
        t = self.camera
        for u in board.adj:
            un = board.get_node(u)
            if not un:
                continue
            sx1, sy1 = t.world_to_screen(un.x, un.y)
            for v in board.adj[u]:
                if v <= u:
                    continue
                vn = board.get_node(v)
                if not vn:
                    continue
                sx2, sy2 = t.world_to_screen(vn.x, vn.y)
                pygame.draw.line(self.bg_cache, ROAD_COLOR, (int(sx1), int(sy1)), (int(sx2), int(sy2)), max(3, int(6 * t.scale)))

        # 绘制节点基础边框
        nr = t.scaled_radius(NODE_RENDER_RADIUS)
        nr_hq = nr + max(1, int(4 * t.scale))
        for nid, nd in board.nodes.items():
            sx, sy = t.world_to_screen(nd.x, nd.y)
            half = nr_hq if nd.is_hq else nr
            tile_rect = pygame.Rect(int(sx) - half, int(sy) - half, half * 2, half * 2)
            pygame.draw.rect(self.bg_cache, TERRAIN_COLOR.get(nd.terrain_key, FALLBACK_GRAY), tile_rect, border_radius=TILE_ROUND_RADIUS)
            pygame.draw.rect(self.bg_cache, (60, 60, 70), tile_rect, max(2, int(3 * t.scale)), border_radius=TILE_ROUND_RADIUS)
        self.bg_dirty = False

    def _draw_info_bar(self, surface):
        if not self.game:
            return
        font = get_font(20, bold=True, style="chinese")
        red_pts = self.game.red.star_points
        blue_pts = self.game.blue.star_points
        info_txt = f"红方得分: {red_pts} \u2605    |    蓝方得分: {blue_pts} \u2605    (胜负目标: {self.game.star_win_goal} \u2605)"
        txt_surf = font.render(info_txt, True, TOY_COLORS["dark_text"])
        surface.blit(txt_surf, (self.manager.WIN_W // 2 - txt_surf.get_width() // 2, 20))