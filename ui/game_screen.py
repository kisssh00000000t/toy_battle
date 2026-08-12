"""
对战游戏界面。

复用 GameState 逻辑层，绘制棋盘、手牌卡片、可放置节点高亮、回合信息。
增加了多行自适应Tooltip支持，地块堆叠堆栈的全览显示，
以及完美修复撤销串牌Bug和自动跳过无目标技能的顺滑逻辑。
"""

import logging
import math
import json
import time
from pathlib import Path

import pygame

from .base_screen import BaseScreen, play_stagger_spawn
from .floating_text import FloatingTextManager
from .turn_banner import TurnBanner
from .board_background import build_board_background, draw_area_tints
from .widgets import (
    ToyButton, ToyCard, TOY_COLORS,
    NumAnimateLabel, draw_rounded_rect, lighten_color, darken_color,
    get_font, get_border_color, build_card_back, draw_drop_shadow,
)
from .render_cache import get_cached_troop, get_cached_terrain, get_cached_star
from .drag_drop import DragDropManager
from .tween_manager import TWEEN
from .easing import EASE_SINE_IN_OUT, EASE_CUBIC_OUT
from .ui_const import (
    BG_CREAM, BORDER_HOVER, BORDER_WHITE,
    ROAD_COLOR, AREA_BOUNDS_COLORS, TEXT_MUTED,
    GRID_TILE_SIZE, GRID_LINE_COLOR, GRID_LINE_WIDTH,
    FACTION_BG_ALPHA, CAMERA_FIT_PADDING,
    TOY_RED_BORDER, TOY_BLUE_BORDER,
    FALLBACK_GRAY,
    OPP_CARD_W, OPP_CARD_H, OPP_CARD_GAP, OPP_CARD_Y,
    DISCARD_PILE_X, DISCARD_PILE_Y,
    RADIUS_SM,
)
from .ui_utils import make_grid_tile, tile_blit_grid, draw_alpha_rect, draw_tooltip
from .camera import Camera
from .ui_manager import UIManager
from game.game_logic import GameState
from game.commands import GameCommand
from game.dispatcher import ActionDispatcher
from game.map_loader import load_map
from game.sound import play as play_sound, SND_CLICK, SND_PLACE, SND_DRAW, SND_WIN, SND_TURN, SND_UNDO, SND_ERROR, SND_STAR, SND_DESTROY, SND_SEAL, SND_RECALL, SND_MOVE, SND_HOVER
from .ui_effects import VignetteEffect, draw_toy_plastic_road
from game.constants import (
    TERRAIN_COLOR, TERRAIN_DATA, PLAYER_COLORS,
    NODE_RENDER_RADIUS, NODE_CLICK_RADIUS,
    HAND_CARD_W, HAND_CARD_H, HAND_Y,
    TILE_ROUND_RADIUS, TILE_PADDING,
    TEAM_BG_ALPHA,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  游戏界面
# ═══════════════════════════════════════════════════════════

class GameScreen(BaseScreen):
    """对战游戏界面。"""

    INFO_BAR_H = 140
    HAND_AREA_H = 160
    SIDE_MARGIN = 10

    def __init__(self, manager, map_data=None, game_mode="local", net_client=None, is_host=True, init_game_state=None):
        super().__init__(manager)
        self.game = GameState()
        self.map_source = "custom"
        if map_data is not None:
            self._map_data_dict = map_data
            self.game.board.load_from_dict(map_data)
            self.map_source = "custom_map"
        else:
            self._map_data_dict = load_map()
            self.game.board.load_from_dict(self._map_data_dict)
            self.map_source = "random"
        self.game.setup()

        self.dispatcher = ActionDispatcher(self.game)
        self.dispatcher.on_action_executed = self._on_dispatcher_executed
        self.game.action_log = self.dispatcher.action_log

        if init_game_state is not None:
            self.game.from_dict(init_game_state)
            self.net_waiting_sync = False

        self.game_mode = game_mode
        self.net_client = net_client
        self.is_host = is_host
        self.local_player_color = "red" if is_host else "blue"
        self.net_waiting_sync = (game_mode == "net" and not is_host and init_game_state is None)
        self.watchdog_timer = 0.0

        try:
            from game.ai_bot import AIBot
            self.ai_bot = AIBot("blue") if game_mode == "ai" else None
        except ImportError:
            self.ai_bot = None
        self.ai_timer = 0.0

        self.selected_troop = None
        self.valid_nodes = []
        self.hover_node = None
        self.hover_alpha = 0
        self._prev_hover_nid = None

        self.tooltip_text = ""
        self.tooltip_pos = (0, 0)
        self.tooltip_timer = 0
        
        self.status_msg = ""
        self.status_timer = 0

        self.game_over_shown = False

        self.btn_draw = ToyButton(
            "抽卡", rect=(20, 720, 120, 50), callback=self._do_draw,
            color=TOY_COLORS["secondary_cyan"], icon_type="draw"
        )
        self.btn_end = ToyButton(
            "结束回合", rect=(160, 720, 140, 50), callback=self._do_end_turn,
            color=TOY_COLORS["accent_coral"], icon_type="end"
        )
        self.btn_undo = ToyButton(
            "撤销", rect=(320, 720, 100, 50), callback=self._undo_action,
            color=TOY_COLORS["soft_blue"], icon_type="back"
        )
        self.btn_back = ToyButton(
            "返回菜单", rect=(1100, 720, 160, 50), callback=self._go_back,
            color=TOY_COLORS["danger_red"], icon_type="back"
        )

        if game_mode == "net":
            self.btn_undo.enabled = False

        self.red_star_label = NumAnimateLabel("0", (20, 40), font_size=20, color=PLAYER_COLORS["red"])
        self.blue_star_label = NumAnimateLabel("0", (20, 65), font_size=20, color=PLAYER_COLORS["blue"])
        self._prev_red_stars = 0
        self._prev_blue_stars = 0

        self.drag_mgr = DragDropManager()
        self.drag_mgr.on_drop_callback = self._on_drop_troop
        self.drag_mgr.find_target_func = self._find_board_node

        self.bg_cache = None
        self.bg_dirty = True
        self._grid_tile_surf = make_grid_tile(GRID_TILE_SIZE, GRID_LINE_COLOR, GRID_LINE_WIDTH)

        self.hq_alpha = 200
        self.placement_pulse_scale = 1.0

        self.skill_target_nodes = []
        self.skill_pulse_time = 0.0

        self._state_snapshots = []

        from game.particle import ParticleSystem
        self.particles = ParticleSystem()
        self.vignette = VignetteEffect((self.manager.WIN_W, self.manager.WIN_H))

        # 浮动文字
        self.floats = FloatingTextManager()
        # 回合横幅
        self.turn_banner = TurnBanner()
        # 卡背缓存
        self._card_back_surf = build_card_back(OPP_CARD_W, OPP_CARD_H)
        # 胜利礼花标记
        self._victory_emitted = False
        # 记录上一回合玩家（用于检测回合切换）
        self._prev_turn_color = self.game.current_player_color

        self.camera = Camera(self.manager.WIN_W, self.manager.WIN_H)
        self.calc_map_transform()

        self.ui_mgr = UIManager(self.camera)
        self.ui_mgr.set_callbacks(
            on_deselect=self._deselect_all,
            on_clear_tooltips=self._clear_tooltips,
            on_get_base_pos=self._get_current_hq_pos,
        )

        self.widgets = [self.btn_draw, self.btn_end, self.btn_undo, self.btn_back]
        play_stagger_spawn(self, anim_dur=0.3, gap=0.06, overlap_ratio=0.3)

        if self.game_mode == "net" and self.is_host and self.net_client:
            self._sync_init_to_client()

        try:
            from game.music_player import BGM
            BGM.play_battle_bgm()
        except Exception as e:
            logger.warning(f"战斗BGM启动失败: {e}")

    def calc_map_transform(self):
        board = self.game.board
        if not board.nodes:
            self.camera.offset_x = 0.0
            self.camera.offset_y = 0.0
            self.camera.zoom = 1.0
            self.camera.dirty = True
            return

        pad = NODE_RENDER_RADIUS + 8
        min_x = min(nd.x - pad for nd in board.nodes.values())
        min_y = min(nd.y - pad for nd in board.nodes.values())
        max_x = max(nd.x + pad for nd in board.nodes.values())
        max_y = max(nd.y + pad for nd in board.nodes.values())

        view_rect = (self.SIDE_MARGIN, self.INFO_BAR_H,
                     self.manager.WIN_W - self.SIDE_MARGIN * 2,
                     self.manager.WIN_H - self.INFO_BAR_H - self.HAND_AREA_H)

        self.camera.fit_to_world(
            world_bounds=(min_x, min_y, max_x, max_y),
            view_rect=view_rect,
            padding_ratio=CAMERA_FIT_PADDING,
        )

    def on_window_resize(self):
        self.camera.on_resize(self.manager.WIN_W, self.manager.WIN_H)
        self.calc_map_transform()
        self._grid_tile_surf = make_grid_tile(GRID_TILE_SIZE, GRID_LINE_COLOR, GRID_LINE_WIDTH)
        self.vignette.set_size((self.manager.WIN_W, self.manager.WIN_H))

    def _handle_game_over(self):
        if self.game_over_shown: return
        self.game_over_shown = True
        self._victory_emitted = False
        self.net_waiting_sync = False
        play_sound(SND_WIN)

        try:
            from game.music_player import BGM
            BGM.play_victory_bgm()
        except Exception as e:
            logger.warning(f"胜利BGM启动失败: {e}")

        try:
            from game.replay import export_replay
            replays_dir = Path(__file__).parent.parent / "replays"
            replays_dir.mkdir(parents=True, exist_ok=True)
            winner = self.game.winner or "draw"
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"replay_{timestamp}_{winner}.json"
            save_path = replays_dir / filename
            export_replay(self.game, self.map_source, save_path)
        except Exception as e:
            logger.warning(f"export_replay 失败: {e}")

        from .modals import GameOverModal
        modal = GameOverModal(
            self.manager, self.game,
            map_source=self.map_source,
            game_mode=self.game_mode,
            win_w=self.manager.WIN_W, win_h=self.manager.WIN_H,
        )
        self.ui_mgr.push_modal(modal)

    def _show_pause_modal(self):
        from .modals import PauseModal
        modal = PauseModal(
            self.manager, self.game,
            map_source=self.map_source,
            win_w=self.manager.WIN_W, win_h=self.manager.WIN_H,
        )
        self.ui_mgr.push_modal(modal)

    def _do_draw(self):
        if self.game.game_over: return
        if self._state_snapshots:
            self.status_msg = "本回合已放置单位，无法抽卡"
            self.status_timer = 90
            play_sound(SND_ERROR)
            return
        cmd = GameCommand("DRAW_CARD", source_player=self.game.current_player_color)
        ok, _ = self.dispatcher.dispatch(cmd)
        if ok and self.game_mode == "net" and self.net_client:
            self.net_client.send_action(cmd.to_dict())
        self._state_snapshots.clear()

    def _do_end_turn(self):
        if self.game.game_over: return
        cmd = GameCommand("END_TURN", source_player=self.game.current_player_color)
        ok, _ = self.dispatcher.dispatch(cmd)
        if ok:
            self._state_snapshots.clear()
            if self.game_mode == "net" and self.net_client:
                self.net_client.send_action(cmd.to_dict())

    def _save_snapshot(self):
        import copy
        self._state_snapshots.append({
            "game": copy.deepcopy(self.game.to_dict()),
            "seq_id": self.dispatcher.current_seq_id,
            "log_len": len(self.dispatcher.action_log),
        })

    def _undo_action(self):
        """快照式撤销：从深拷贝恢复完整游戏状态。"""
        if self.game_mode == "net":
            return
        if self.game.game_over or self.game.pending_skill or getattr(self.game, 'pending_selection', None):
            return
        if not self._state_snapshots:
            self.status_msg = "无可撤销操作"
            self.status_timer = 60
            play_sound(SND_ERROR)
            return
        snap = self._state_snapshots.pop()
        self.game.from_dict(snap["game"])
        self.dispatcher.current_seq_id = snap["seq_id"]
        del self.dispatcher.action_log[snap["log_len"]:]
        self.game.action_log = self.dispatcher.action_log
        self.selected_troop = None
        self.valid_nodes = []
        self.bg_dirty = True
        self.status_msg = "已撤销"
        self.status_timer = 60
        play_sound(SND_UNDO)

    def _play_effect_sounds(self):
        msg = self.game.turn_msg
        if "清除" in msg: play_sound(SND_DESTROY)
        if "封印" in msg: play_sound(SND_SEAL)
        if "召回" in msg or "回收" in msg: play_sound(SND_RECALL)
        if "移动" in msg: play_sound(SND_MOVE)

    def _on_dispatcher_executed(self, cmd: GameCommand, ok: bool, msg: str):
        if not ok:
            self.status_msg = msg
            self.status_timer = 90
            play_sound(SND_ERROR)
            return

        self.bg_dirty = True

        if cmd.action_type == "DRAW_CARD":
            play_sound(SND_DRAW)
            self.status_msg = msg
            self.status_timer = 60

        elif cmd.action_type == "PLAY_PIECE":
            node_id = cmd.payload.get("node_id")
            node = self.game.board.get_node(int(node_id)) if node_id is not None else None
            if node:
                self._emit_place_particles(node)
            play_sound(SND_PLACE)
            self._play_effect_sounds()

            # 浮动文字：覆盖/自毁等
            if node and node.top_troop:
                sx, sy = self.camera.world_to_screen(node.x, node.y)
                placed_name = node.top_troop.name
                msg = self.game.turn_msg or ""
                if "自毁" in msg or "爆弹" in msg:
                    self.floats.emit("BOOM!", sx, sy, (255, 80, 80), 36)
                    self.camera.add_shake(10)
                elif "回旋" in msg:
                    self.floats.emit("回旋!", sx, sy, (100, 200, 255), 24)
                elif "队长" in placed_name:
                    self.floats.emit("再置!", sx, sy, (255, 200, 50), 22)

            if self.game.game_over:
                self._handle_game_over()
            elif self.game.extra_place_pending:
                self.status_msg = "玩具队长：可再放置一张！"
                self.status_timer = 90
            else:
                self.status_msg = "放置成功！请点击「结束回合」"
                self.status_timer = 90

        elif cmd.action_type == "END_TURN":
            play_sound(SND_TURN)
            self.camera.add_shake(2)
            self.status_msg = f"轮到 {self.game.current_player_color.upper()} 方行动"
            self.status_timer = 60

        elif cmd.action_type == "SYNC_INIT":
            self.calc_map_transform()
            self.bg_dirty = True

        elif cmd.action_type == "CAST_SKILL":
            play_sound(SND_MOVE)
            if msg:
                self.status_msg = msg
                self.status_timer = 90
            self.skill_target_nodes = []
            self.skill_pulse_time = 0.0
            # 技能效果浮动文字
            if msg:
                if "牵引" in msg or "拉动" in msg:
                    self.floats.emit("牵引!", 0, 0, (180, 130, 255), 22)
                elif "击杀" in msg or "消灭" in msg:
                    self.camera.add_shake(5)
                elif "失败" in msg or "无法" in msg:
                    self.floats.emit("失败!", 0, 0, (255, 180, 50), 20)

        self.selected_troop = None
        self.valid_nodes = []

    def _go_back(self):
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def _deselect_all(self):
        if self.selected_troop is not None or self.valid_nodes:
            self.selected_troop = None
            self.valid_nodes = []
            return True
        return False

    def _clear_tooltips(self):
        self.tooltip_text = ""
        self.tooltip_timer = 0
        self.hover_node = None
        self.hover_alpha = 0

    def _get_current_hq_pos(self):
        cp_color = self.game.current_player_color
        for nid, node in self.game.board.nodes.items():
            if node.is_hq and node.hq_owner == cp_color:
                return (node.x, node.y)
        nodes = list(self.game.board.nodes.values())
        if nodes:
            cx = sum(n.x for n in nodes) / len(nodes)
            cy = sum(n.y for n in nodes) / len(nodes)
            return (cx, cy)
        return None

    def handle_event(self, event):
        if self.game_mode == "net" and self.net_client is not None:
            if self.net_waiting_sync or self.game.current_player_color != self.local_player_color:
                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.KEYDOWN):
                    if not self.net_waiting_sync:
                        self.status_msg = "正等待网络对手下棋中..."
                        self.status_timer = 40
                    return

        super().handle_event(event)

        if self.ui_mgr.has_modal:
            self.ui_mgr.handle_event(event)
            return

        if self.game.game_over:
            return

        if self.game_mode == "ai" and self.ai_bot is not None:
            if self.game.current_player_color == self.ai_bot.player_color:
                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                    return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if getattr(self.game, 'pending_skill', None):
                self._undo_action()
                self.status_msg = "已取消技能释放，收回该兵种"
                self.status_timer = 90
                return
            if not self.selected_troop and not self.valid_nodes and not self.tooltip_timer:
                self._show_pause_modal()
                return

        if self.ui_mgr.handle_event(event):
            if self.camera.dirty:
                self.bg_dirty = True
                self.camera.dirty = False
            return

        if self.drag_mgr.handle_event(event):
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos

            # ── pending_selection 选择模式 ──
            if getattr(self.game, 'pending_selection', None):
                sel = self.game.pending_selection
                if event.button == 1:
                    handled = self._handle_selection_click(event.pos, sel)
                    if handled:
                        return
                elif event.button == 3:
                    if sel.get("cancellable"):
                        self._dispatch_select(None)
                    return

            # ── 右键跳过技能选择 (交由后端正规处理) ──
            if event.button == 3:
                if getattr(self.game, 'pending_skill', None):
                    cmd = GameCommand(
                        "CAST_SKILL",
                        source_player=self.game.current_player_color,
                        payload={"target_nid": None},
                    )
                    # 走正规通道，后端会返回 True 并自己结束回合
                    ok, msg = self.dispatcher.dispatch(cmd)
                    if ok:
                        if self.game_mode == "net" and self.net_client:
                            self.net_client.send_action(cmd.to_dict())
                        self.status_msg = "已跳过该技能"
                        self.status_timer = 60
                    else:
                        self.status_msg = f"无法跳过: {msg}"
                        self.status_timer = 90
                    self.bg_dirty = True
                    return

            if event.button == 1:
                if self.game.pending_skill:
                    t = self.camera
                    wx, wy = t.screen_to_world(mx, my)
                    click_r = t.scaled_click_radius(NODE_CLICK_RADIUS + 6)
                    clicked_node = self.game.board.get_node_by_pos(wx, wy, radius=click_r)
                    if clicked_node is not None and clicked_node in self.skill_target_nodes:
                        self._save_snapshot()
                        cmd = GameCommand(
                            "CAST_SKILL",
                            source_player=self.game.current_player_color,
                            payload={"target_nid": clicked_node.nid},
                        )
                        ok, _ = self.dispatcher.dispatch(cmd)
                        if ok:
                            if self.game_mode == "net" and self.net_client:
                                self.net_client.send_action(cmd.to_dict())
                        else:
                            self.status_msg = self.game.turn_msg
                            self.status_timer = 90
                    return

                troop = self._hit_hand_card(mx, my)
                if troop is not None:
                    play_sound(SND_CLICK)
                    self.selected_troop = troop
                    self.valid_nodes = self.game.get_valid_nodes(troop)
                    drag_img = self._make_troop_drag_image(troop)
                    card_rect = self._get_hand_card_rect(troop)
                    self.drag_mgr.start_drag(troop, card_rect, drag_img)
                    return

                if self.selected_troop is not None:
                    t = self.camera
                    wx, wy = t.screen_to_world(mx, my)
                    click_r = t.scaled_click_radius(NODE_CLICK_RADIUS + 6)
                    node = self.game.board.get_node_by_pos(wx, wy, radius=click_r)
                    if node is not None and node in self.valid_nodes:
                        self._save_snapshot()
                        
                        placed_troop = self.selected_troop
                        player_col = self.game.current_player_color
                        
                        cmd = GameCommand(
                            "PLAY_PIECE",
                            source_player=player_col,
                            payload={"troop_key": placed_troop.troop_key, "node_id": node.nid},
                        )
                        ok, _ = self.dispatcher.dispatch(cmd)
                        if ok:
                            self.selected_troop = None
                            self.valid_nodes = []
                            
                            # 自动跳过无目标的技能，极致顺滑
                            if getattr(self.game, 'pending_skill', None):
                                self.skill_target_nodes = self.game.get_skill_target_nodes()
                                if not self.skill_target_nodes:
                                    cmd_skip = GameCommand("CAST_SKILL", source_player=self.game.current_player_color, payload={"target_nid": None})
                                    ok_skip, _ = self.dispatcher.dispatch(cmd_skip)
                                    if ok_skip and self.game_mode == "net" and self.net_client:
                                        self.net_client.send_action(cmd_skip.to_dict())
                                    self.status_msg = "无合法技能目标，已自动跳过"
                                    self.status_timer = 90
                            
                            if self.game_mode == "net" and self.net_client:
                                self.net_client.send_action(cmd.to_dict())
                        else:
                            self.status_msg = self.game.turn_msg
                            self.status_timer = 90
                    else:
                        self.selected_troop = None
                        self.valid_nodes = []

        elif event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            t = self.camera
            wx, wy = t.screen_to_world(mx, my)
            hover_r = t.scaled_click_radius(NODE_CLICK_RADIUS)
            self.hover_node = self.game.board.get_node_by_pos(wx, wy, hover_r)
            if self.hover_node:
                new_nid = self.hover_node.nid
                if new_nid != self._prev_hover_nid:
                    play_sound(SND_HOVER)
                    self._prev_hover_nid = new_nid
                TWEEN.create_tween(self, "hover_alpha", 255, 0.15, 0, EASE_CUBIC_OUT)
            else:
                TWEEN.create_tween(self, "hover_alpha", 0, 0.1, 0, EASE_CUBIC_OUT)
                
            troop = self._hit_hand_card(mx, my)
            if troop is not None:
                from game.constants import TROOP_DATA
                t_data = TROOP_DATA.get(troop.troop_key, {})
                t_desc = t_data.get("desc", "")
                desc_text = ""
                if t_desc:
                    wrapped_desc = "\n".join(t_desc[i:i+16] for i in range(0, len(t_desc), 16))
                    desc_text = f"\n\n技能说明:\n{wrapped_desc}"
                
                self.tooltip_text = f"【{troop.name}】 {troop.alias}  战力: {troop.number or 'J'}{desc_text}"
                self.tooltip_pos = (mx + 15, my - 25)
                self.tooltip_timer = 60

    def _hit_hand_card(self, mx, my):
        cp = self.game.current_player
        hand = cp.hand
        if not hand:
            return None
        total_w = len(hand) * (HAND_CARD_W + 8) - 8
        start_x = (self.manager.WIN_W - total_w) // 2
        for i, troop in enumerate(hand):
            card_x = start_x + i * (HAND_CARD_W + 8)
            card_y = HAND_Y
            rect = pygame.Rect(card_x, card_y, HAND_CARD_W, HAND_CARD_H)
            if rect.collidepoint(mx, my):
                return troop
        return None

    def _get_hand_card_rect(self, troop):
        cp = self.game.current_player
        hand = cp.hand
        if troop not in hand:
            return pygame.Rect(0, 0, HAND_CARD_W, HAND_CARD_H)
        i = hand.index(troop)
        total_w = len(hand) * (HAND_CARD_W + 8) - 8
        start_x = (self.manager.WIN_W - total_w) // 2
        card_x = start_x + i * (HAND_CARD_W + 8)
        return pygame.Rect(card_x, HAND_Y, HAND_CARD_W, HAND_CARD_H)

    def _make_troop_drag_image(self, troop):
        w, h = HAND_CARD_W, HAND_CARD_H
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, w, h)
        card = ToyCard(troop, rect, selected=True,
                       player_color_name=self.game.current_player_color)
        cp_color = PLAYER_COLORS.get(self.game.current_player_color, FALLBACK_GRAY)
        card.draw(surf, cp_color)
        return surf

    def _find_board_node(self, mx, my):
        t = self.camera
        wx, wy = t.screen_to_world(mx, my)
        click_r = t.scaled_click_radius(NODE_CLICK_RADIUS + 10)
        return self.game.board.get_node_by_pos(wx, wy, radius=click_r)

    def _on_drop_troop(self, troop, node):
        if troop is None or node is None:
            return
        valid = self.game.get_valid_nodes(troop)
        if node in valid:
            self._save_snapshot()
            
            player_col = self.game.current_player_color
            cmd = GameCommand(
                "PLAY_PIECE",
                source_player=player_col,
                payload={"troop_key": troop.troop_key, "node_id": node.nid},
            )
            ok, _ = self.dispatcher.dispatch(cmd)
            
            # 自动跳过无目标的技能，极致顺滑
            if getattr(self.game, 'pending_skill', None):
                self.skill_target_nodes = self.game.get_skill_target_nodes()
                if not self.skill_target_nodes:
                    cmd_skip = GameCommand("CAST_SKILL", source_player=self.game.current_player_color, payload={"target_nid": None})
                    ok_skip, _ = self.dispatcher.dispatch(cmd_skip)
                    if ok_skip and self.game_mode == "net" and self.net_client:
                        self.net_client.send_action(cmd_skip.to_dict())
                    self.status_msg = "无合法技能目标，已自动跳过"
                    self.status_timer = 90
            
            if self.game_mode == "net" and self.net_client:
                self.net_client.send_action(cmd.to_dict())
        else:
            self.status_msg = self.game.turn_msg
            self.status_timer = 90
        self.selected_troop = None
        self.valid_nodes = []

    # ── pending_selection UI 处理 ──

    def _handle_selection_click(self, pos, sel):
        stype = sel["type"]

        if stype in ("recall", "yoyo_target"):
            # 点击地图节点 — 使用 camera 坐标变换
            mx, my = pos
            t = self.camera
            wx, wy = t.screen_to_world(mx, my)
            click_r = t.scaled_click_radius(NODE_CLICK_RADIUS + 6)
            clicked_node = self.game.board.get_node_by_pos(wx, wy, radius=click_r)
            if clicked_node is not None:
                nid = clicked_node.nid
                if any(o["id"] == nid for o in sel["options"]):
                    self._dispatch_select(nid)
                    return True
            return False

        elif stype == "recover_discard":
            # 点击弃牌堆弹窗中的牌
            return self._handle_discard_pile_click(pos, sel)

        elif stype == "seal":
            # 点击对手手牌区域（背面）
            return self._handle_seal_click(pos, sel)

        return False

    def _dispatch_select(self, option_id):
        cmd = GameCommand(
            "SELECT_TARGET",
            source_player=self.game.current_player_color,
            payload={"option_id": option_id},
        )
        self.dispatcher.dispatch(cmd)
        self._refresh_all_sprites()

    def _handle_discard_pile_click(self, pos, sel):
        """弃牌堆选择弹窗点击检测。"""
        pg = pygame
        card_w, card_h = 70, 100
        gap = 16
        total = len(sel["options"])
        total_w = total * card_w + (total - 1) * gap
        
        # 坐标需与渲染界面严格对齐
        pw, ph = max(total_w + 80, 400), card_h + 140
        px = (self.manager.WIN_W - pw) // 2
        py = (self.manager.WIN_H - ph) // 2
        start_x = px + (pw - total_w) // 2
        card_y = py + 80
        
        for i, opt in enumerate(sel["options"]):
            rect = pg.Rect(start_x + i * (card_w + gap), card_y, card_w, card_h)
            if rect.collidepoint(pos):
                self._dispatch_select(opt["id"])
                return True
        return False

    def _handle_seal_click(self, pos, sel):
        """对手手牌背面点击（使用OPP_CARD常量）。"""
        opp_color = "blue" if self.game.current_player_color == "red" else "red"
        opp = getattr(self.game, opp_color, None)
        if not opp: return False
        n = len(opp.hand)
        if n == 0: return False
        
        cw, ch, gap = OPP_CARD_W, OPP_CARD_H, OPP_CARD_GAP
        total_w = n * cw + (n - 1) * gap
        start_x = self.manager.WIN_W - total_w - 20
        y = OPP_CARD_Y
        
        for i in range(n):
            rect = pygame.Rect(start_x + i * (cw + gap), y, cw, ch)
            if rect.collidepoint(pos):
                self._dispatch_select(i)
                return True
        return False

    def _refresh_all_sprites(self):
        """刷新所有节点精灵（选择后状态变化）。"""
        self.bg_dirty = True
        self.selected_troop = None
        self.valid_nodes = []
        self.skill_target_nodes = []
        self.skill_pulse_time = 0.0

    def update(self, dt):
        self.camera.update(dt)
        if self.camera.dirty:
            self.bg_dirty = True
            self.camera.dirty = False

        if self.tooltip_timer > 0:
            self.tooltip_timer -= 1
            
        if self.status_timer > 0:
            self.status_timer -= 1

        if self.game.game_over and not self.game_over_shown:
            self._handle_game_over()
            
        red_stars = self.game.red.star_points
        blue_stars = self.game.blue.star_points
        if red_stars != self._prev_red_stars:
            self.red_star_label.set_value(red_stars)
            self._prev_red_stars = red_stars
            self._emit_star_capture_particles("red")
            play_sound(SND_STAR)
        if blue_stars != self._prev_blue_stars:
            self.blue_star_label.set_value(blue_stars)
            self._prev_blue_stars = blue_stars
            self._emit_star_capture_particles("blue")
            play_sound(SND_STAR)

        # 回合切换横幅
        cur_color = self.game.current_player_color
        if cur_color != self._prev_turn_color and not self.game.game_over:
            self.turn_banner.show(
                f"{'红' if cur_color == 'red' else '蓝'}方回合",
                PLAYER_COLORS.get(cur_color, FALLBACK_GRAY),
                "请选择手牌或抽卡"
            )
            self._prev_turn_color = cur_color
            
        if self.valid_nodes and not hasattr(self, '_pulse_tween_active'):
            self._pulse_tween_active = True
            TWEEN.create_tween(self, "placement_pulse_scale", 1.15, 0.4, 0, EASE_SINE_IN_OUT)
        elif not self.valid_nodes:
            self._pulse_tween_active = False
            self.placement_pulse_scale = 1.0

        if self.game.pending_skill:
            self.skill_pulse_time += dt
            current_targets = self.game.get_skill_target_nodes()
            if current_targets != self.skill_target_nodes:
                self.skill_target_nodes = current_targets
        else:
            if self.skill_target_nodes:
                self.skill_target_nodes = []
            self.skill_pulse_time = 0.0

        self.particles.update()

        self.floats.update(dt)
        self.turn_banner.update(dt)

        if self.net_waiting_sync:
            self.watchdog_timer += dt
            if self.watchdog_timer >= 3.5:
                self.watchdog_timer = 0.0
                if self.net_client:
                    self.net_client.send_action({"act_type": "REQ_SYNC_SNAPSHOT"})
                self.status_msg = "同步连接轻微延迟，正在自动请求对齐..."
                self.status_timer = 60

        if self.ai_bot is not None and not self.game.game_over:
            self.update_ai_turn(dt)

        self._update_net_messages()

    def update_ai_turn(self, dt):
        self.ai_timer += dt
        if self.ai_timer < 0.55: return
        self.ai_timer = 0.0
        if self.game.current_player.color != self.ai_bot.player_color: return
        action = self.ai_bot.decide_action(self.game)
        self._execute_ai_action(action)

    def _execute_ai_action(self, action: dict):
        atype = action.get("type")
        if atype == "place":
            cmd = GameCommand("PLAY_PIECE", source_player=self.ai_bot.player_color,
                              payload={"troop_key": action.get("troop_key"), "node_id": action.get("target_nid")})
            self.dispatcher.dispatch(cmd)
        elif atype == "cast_skill":
            cmd = GameCommand("CAST_SKILL", source_player=self.ai_bot.player_color,
                              payload={"target_nid": action.get("target_nid")})
            self.dispatcher.dispatch(cmd)
        elif atype == "select":
            cmd = GameCommand("SELECT_TARGET", source_player=self.ai_bot.player_color,
                              payload={"option_id": action.get("option_id")})
            self.dispatcher.dispatch(cmd)
        elif atype == "undo":
            self._undo_action()
        elif atype == "draw":
            cmd = GameCommand("DRAW_CARD", source_player=self.ai_bot.player_color)
            self.dispatcher.dispatch(cmd)
        elif atype == "end_turn":
            cmd = GameCommand("END_TURN", source_player=self.ai_bot.player_color)
            self.dispatcher.dispatch(cmd)

    def _update_net_messages(self):
        if self.game_mode != "net" or not self.net_client: return
        while True:
            msg = self.net_client.get_message(timeout=0.0)
            if not msg: break
            msg_type = msg.get("type")
            if msg_type != "action": continue
            payload = msg.get("payload", {})
            if payload.get("act_type") == "REQ_SYNC_SNAPSHOT" and self.is_host:
                self._sync_init_to_client()
                continue
            if "action_type" in payload and "seq_id" in payload:
                cmd = GameCommand.from_dict(payload)
                self.dispatcher.dispatch(cmd, is_remote=True)
                if cmd.action_type == "SYNC_INIT":
                    self.net_waiting_sync = False
                    self.watchdog_timer = 0.0
            else:
                act_type = payload.get("act_type")
                if act_type == "sync_init":
                    self._apply_sync_init(payload)
                    self.net_waiting_sync = False
                    self.watchdog_timer = 0.0
                elif act_type == "place":
                    cmd = GameCommand("PLAY_PIECE", source_player=payload.get("player", "blue"),
                                      payload={"troop_key": str(payload.get("troop_key")), "node_id": int(payload.get("node_id", -1))})
                    self.dispatcher.dispatch(cmd, is_remote=True)
                elif act_type == "draw":
                    cmd = GameCommand("DRAW_CARD", source_player=payload.get("player", "blue"))
                    self.dispatcher.dispatch(cmd, is_remote=True)
                elif act_type == "end_turn":
                    cmd = GameCommand("END_TURN", source_player=payload.get("player", "blue"))
                    self.dispatcher.dispatch(cmd, is_remote=True)

    def _net_send_action(self, act_type: str, **kwargs):
        if self.game_mode != "net" or not self.net_client: return
        payload = {"act_type": act_type, "player": self.local_player_color}
        payload.update(kwargs)
        self.net_client.send_action(payload)

    def _sync_init_to_client(self):
        if not self.net_client: return
        cmd = GameCommand("SYNC_INIT", source_player="system",
                          payload={"map_data": self._map_data_dict, "game_state": self.game.to_dict()})
        self.net_client.send_action(cmd.to_dict())

    def _apply_sync_init(self, payload: dict):
        try:
            if "map_data" in payload:
                self.game.board.load_from_dict(payload["map_data"])
                self._map_data_dict = payload["map_data"]
            if "game_state" in payload:
                self.game.from_dict(payload["game_state"])
            self.calc_map_transform()
            self.bg_dirty = True
            self.net_waiting_sync = False
            self.watchdog_timer = 0.0
            logger.info("辅机 sync_init 同步完成，游戏状态已恢复")
        except Exception as e:
            logger.error(f"辅机 sync_init 恢复异常: {e}")

    def draw(self, surface):
        surface.fill(TOY_COLORS["bg_cream"])
        self._draw_board(surface)
        self._draw_opponent_hand(surface)
        self._draw_hand(surface)
        self._draw_info(surface)
        self._draw_discard_pile(surface)
        self._draw_status_msg(surface)

        # ── pending_selection 选择提示和高亮 ──
        if getattr(self.game, 'pending_selection', None):
            sel = self.game.pending_selection
            
            # 【修复 BUG & 优化】针对磁钩或召回地块的动态高光
            if sel["type"] in ("recall", "yoyo_target"):
                for opt in sel["options"]:
                    node = self.game.board.get_node(opt["id"])
                    if node:
                        t = self.camera
                        sx, sy = t.world_to_screen(node.x, node.y)
                        nr = t.scaled_radius(NODE_RENDER_RADIUS)
                        half = nr + max(1, int(4 * t.scale)) if node.is_hq else nr
                        tile_rect = pygame.Rect(int(sx) - half, int(sy) - half, half * 2, half * 2)
                        
                        # 添加玩具风格的呼吸灯特效
                        pulse = int(4 * math.sin(pygame.time.get_ticks() * 0.005))
                        hl_rect = tile_rect.inflate(8 + pulse, 8 + pulse)
                        pygame.draw.rect(surface, (255, 220, 50), hl_rect, 4, border_radius=TILE_ROUND_RADIUS + 4)
                        pygame.draw.rect(surface, (255, 255, 255), hl_rect.inflate(4, 4), 1, border_radius=TILE_ROUND_RADIUS + 6)
            
            hint = " (右键取消)" if sel.get("cancellable") else ""
            self._draw_hint(f"请选择 {sel['type']} 目标{hint}")
            
            # 【优化】修改传参，使弹窗正确渲染
            if sel["type"] == "recover_discard":
                self._draw_discard_pile_dialog(surface, sel)
            
            # 【优化】修改传参
            if sel["type"] == "seal":
                self._draw_opponent_hand_highlight(surface)
        
        t = self.camera
        valid_set = set(nd.nid for nd in self.valid_nodes) if self.drag_mgr.dragging else None
        valid_check = (lambda tgt: tgt.nid in valid_set) if valid_set is not None else None
        target_pos_func = lambda tgt: t.world_to_screen(tgt.x, tgt.y)
        hl_radius = t.scaled_radius(NODE_RENDER_RADIUS) + int(t.apply_to_size(6))
        hl_width = max(2, int(4 * t.scale))
        self.drag_mgr.draw_target_highlight(surface, target_pos_func=target_pos_func,
                                            valid_check_func=valid_check,
                                            highlight_radius=hl_radius, highlight_width=hl_width)
        self.drag_mgr.draw(surface)
        if self.game.game_over and not self.ui_mgr.has_modal:
            self._draw_game_over(surface)
            
        self._draw_hover_panel(surface)
        self._draw_tooltip(surface)  
        
        self.particles.draw(surface)
        self.floats.draw(surface)
        self.turn_banner.draw(surface)
        self.vignette.render(surface)
        for widget in self.widgets:
            widget.draw(surface)
        self.ui_mgr.draw_modals(surface)
        
        if self.net_waiting_sync:
            overlay = pygame.Surface((self.manager.WIN_W, self.manager.WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            surface.blit(overlay, (0, 0))
            pw, ph = 360, 120
            px, py = self.manager.WIN_W // 2 - pw // 2, self.manager.WIN_H // 2 - ph // 2
            panel_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
            draw_rounded_rect(panel_surf, TOY_COLORS["panel_bg"], panel_surf.get_rect(), radius=16)
            pygame.draw.rect(panel_surf, TOY_COLORS["primary_yellow"], panel_surf.get_rect(), 4, border_radius=16)
            surface.blit(panel_surf, (px, py))
            font = get_font(24, bold=True, style="chinese")
            txt = font.render("等待主机同步中...", True, TOY_COLORS["dark_text"])
            surface.blit(txt, (px + pw // 2 - txt.get_width() // 2, py + ph // 2 - txt.get_height() // 2))

    def _draw_hand(self, surface):
        """绘制当前玩家的手牌区"""
        cp = self.game.current_player
        hand = cp.hand
        if not hand:
            return
            
        player_color = PLAYER_COLORS.get(cp.color, FALLBACK_GRAY)
        total_w = len(hand) * (HAND_CARD_W + 8) - 8
        start_x = (self.manager.WIN_W - total_w) // 2
        
        for i, troop in enumerate(hand):
            card_x = start_x + i * (HAND_CARD_W + 8)
            card_y = HAND_Y
            rect = pygame.Rect(card_x, card_y, HAND_CARD_W, HAND_CARD_H)
            
            # 判断是否是当前选中的卡牌
            selected = (troop is self.selected_troop)
            card = ToyCard(troop, rect, selected=selected, player_color_name=cp.color)
            card.draw(surface, player_color)

    def _draw_info(self, surface):
        """左上角信息栏：回合指示 + 星星 + 牌量。"""
        cp_color = self.game.current_player_color
        player_color = PLAYER_COLORS.get(cp_color, FALLBACK_GRAY)

        # 回合指示圆点
        pygame.draw.circle(surface, player_color, (32, 26), 13)
        pygame.draw.circle(surface, (255, 255, 255), (32, 26), 13, 3)
        font = get_font(22, bold=True, style="chinese")
        label = font.render(f"{cp_color.upper()} 回合", True, player_color)
        surface.blit(label, (52, 14))

        # 红方星星行
        red_prefix = get_font(16, bold=True, style="chinese").render(
            "红", True, PLAYER_COLORS["red"])
        surface.blit(red_prefix, (20, 50))
        for i in range(self.game.star_win_goal):
            state = "red" if i < self.game.red.star_points else "gray"
            s = get_cached_star(state, 11)
            surface.blit(s, (40 + i * 24, 48))

        # 蓝方星星行
        blue_prefix = get_font(16, bold=True, style="chinese").render(
            "蓝", True, PLAYER_COLORS["blue"])
        surface.blit(blue_prefix, (20, 74))
        for i in range(self.game.star_win_goal):
            state = "blue" if i < self.game.blue.star_points else "gray"
            s = get_cached_star(state, 11)
            surface.blit(s, (40 + i * 24, 72))

        # 牌量信息
        small_font = get_font(15, bold=True, style="chinese")
        cp = self.game.current_player
        info_y = 100
        surface.blit(small_font.render(
            f"牌库 {len(cp.reserve)}", True, TOY_COLORS["dark_text"]), (20, info_y))
        surface.blit(small_font.render(
            f"手牌 {len(cp.hand)}", True, TOY_COLORS["dark_text"]), (90, info_y))
        surface.blit(small_font.render(
            f"弃牌 {len(cp.discard)}", True, TOY_COLORS["dark_text"]), (160, info_y))

        # 回合消息
        if self.game.turn_msg:
            msg_font = get_font(15, style="chinese")
            msg_surf = msg_font.render(self.game.turn_msg, True, (90, 90, 100))
            surface.blit(msg_surf, (20, 122))

        # 队长额外放置提示
        if self.game.extra_place_pending:
            extra_font = get_font(20, bold=True, style="chinese")
            extra_surf = extra_font.render("队长：可再放置一张！",
                                           True, TOY_COLORS["accent_coral"])
            surface.blit(extra_surf, (400, 10))

    def _draw_opponent_hand(self, surface):
        """对手手牌：卡背 + 封印标红。"""
        opp_color = "blue" if self.game.current_player_color == "red" else "red"
        opp = getattr(self.game, opp_color, None)
        if opp is None:
            return
        n = len(opp.hand)
        if n == 0:
            return
        cw = OPP_CARD_W
        ch = OPP_CARD_H
        gap = OPP_CARD_GAP
        total_w = n * cw + (n - 1) * gap
        start_x = self.manager.WIN_W - total_w - 20
        y = OPP_CARD_Y
        for i in range(n):
            x = start_x + i * (cw + gap)
            rect = pygame.Rect(x, y, cw, ch)
            surface.blit(self._card_back_surf, rect.topleft)
            pygame.draw.rect(surface, PLAYER_COLORS.get(opp_color, FALLBACK_GRAY),
                             rect, 2, border_radius=RADIUS_SM)
            # 封印标红
            troop = opp.hand[i]
            if hasattr(troop, "sealed") and troop.sealed:
                seal_surf = pygame.Surface((cw, ch), pygame.SRCALPHA)
                seal_surf.fill((255, 0, 0, 50))
                surface.blit(seal_surf, rect.topleft)

    def _draw_discard_pile(self, surface):
        """弃牌堆：侧面牌堆 + 数量 + 标签。"""
        pile = self.game.current_player.discard_pile if hasattr(self.game.current_player, "discard_pile") else []
        n = len(pile)
        x = DISCARD_PILE_X
        y = DISCARD_PILE_Y
        # 牌堆侧面（最多显示5张偏移）
        show = min(n, 5)
        for i in range(show):
            offset = i * 2
            r = pygame.Rect(x + offset, y + offset, 36, 50)
            pygame.draw.rect(surface, (180, 170, 150), r, border_radius=RADIUS_SM)
            pygame.draw.rect(surface, (120, 110, 100), r, 1, border_radius=RADIUS_SM)
        # 数量角标
        if n > 0:
            badge_font = get_font(14, bold=True)
            badge = badge_font.render(str(n), True, (255, 255, 255))
            bx = x + show * 2 + 18
            by = y - 6
            pygame.draw.circle(surface, (60, 60, 60), (bx, by + 8), 12)
            surface.blit(badge, (bx - badge.get_width() // 2, by + 2))
        # 标签
        label_font = get_font(14, style="chinese")
        label = label_font.render("弃牌堆", True, (140, 140, 140))
        surface.blit(label, (x - 4, y + 56))

    def _draw_game_over(self, surface):
        """游戏结束：礼花 + 遮罩 + 结果 + 数据。"""
        # 礼花粒子
        if not self._victory_emitted:
            self._victory_emitted = True
            import random
            for _ in range(8):
                self.particles.emit_victory(
                    random.randint(100, self.manager.WIN_W - 100),
                    random.randint(50, 250))
            self.camera.add_shake(8)

        overlay = pygame.Surface((self.manager.WIN_W, self.manager.WIN_H),
                                 pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 130))
        surface.blit(overlay, (0, 0))

        winner = self.game.winner
        if winner:
            color = PLAYER_COLORS.get(winner, FALLBACK_GRAY)
            text = f"{'红' if winner == 'red' else '蓝'}方胜利！"
        else:
            color = TOY_COLORS["dark_text"]
            text = "平局！"

        font_big = get_font(52, bold=True, style="chinese")
        txt_surf = font_big.render(text, True, color)

        pw = max(txt_surf.get_width() + 100, 420)
        ph = 240
        px = self.manager.WIN_W // 2 - pw // 2
        py = self.manager.WIN_H // 2 - ph // 2 - 20

        panel_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
        draw_rounded_rect(panel_surf, (255, 255, 245, 240),
                          panel_surf.get_rect(), radius=24)
        pygame.draw.rect(panel_surf, color, panel_surf.get_rect(), 6,
                         border_radius=24)
        surface.blit(panel_surf, (px, py))
        surface.blit(txt_surf, (self.manager.WIN_W // 2 - txt_surf.get_width() // 2,
                                py + 24))

        # 数据统计
        stats_font = get_font(18, style="chinese")
        red = self.game.red
        blue = self.game.blue
        stats = [
            f"红方勋章 {red.star_points}    蓝方勋章 {blue.star_points}",
            f"红方剩余 {len(red.hand) + len(red.reserve)}    "
            f"蓝方剩余 {len(blue.hand) + len(blue.reserve)}",
        ]
        for i, s in enumerate(stats):
            s_surf = stats_font.render(s, True, (80, 80, 90))
            surface.blit(s_surf, (self.manager.WIN_W // 2 - s_surf.get_width() // 2,
                                  py + 100 + i * 28))

        tip_font = get_font(16, style="chinese")
        tip = tip_font.render("点击任意位置继续", True, (150, 150, 150))
        surface.blit(tip, (self.manager.WIN_W // 2 - tip.get_width() // 2,
                           py + ph - 36))

    def _emit_place_particles(self, node):
        """放置兵种时在节点位置发射碎屑粒子"""
        t = self.camera
        sx, sy = t.world_to_screen(node.x, node.y)
        troop = node.top_troop
        color = PLAYER_COLORS.get(troop.owner, (200, 200, 200)) if troop else (200, 200, 200)
        self.particles.emit_troop_place(sx, sy, color=color)

    def _emit_star_capture_particles(self, color_name):
        """占领星星时发射粒子 + 浮动文字。"""
        board = self.game.board
        t = self.camera
        player = self.game.red if color_name == "red" else self.game.blue
        star_color = PLAYER_COLORS.get(color_name, (255, 210, 0))

        for sp in board.star_points:
            aid = sp.get("area_id", -1)
            if aid in player.captured_areas:
                wx, wy = sp["x"], sp["y"]
                sx, sy = t.world_to_screen(wx, wy)
                self.particles.emit_star_capture(sx, sy, color=star_color)
                self.floats.emit("★ +1", sx, sy, (255, 210, 0), 28)
                self.camera.add_shake(4)

    def _draw_status_msg(self, surface):
        if self.status_timer > 0 and self.status_msg:
            font = get_font(28, bold=True, style="chinese")
            txt_surf = font.render(self.status_msg, True, TOY_COLORS["dark_text"])
            pw = txt_surf.get_width() + 80
            ph = txt_surf.get_height() + 24
            bg_rect = pygame.Rect(0, 0, pw, ph)
            bg_rect.centerx = self.manager.WIN_W // 2
            bg_rect.y = 80  # 下拉以免盖住顶部 UI
            
            # 添加玩具风阴影
            draw_drop_shadow(surface, bg_rect, radius=18, offset=(0, 6), alpha=50)
            
            bg_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
            draw_rounded_rect(bg_surf, (255, 255, 245, 245), bg_surf.get_rect(), radius=18)
            pygame.draw.rect(bg_surf, TOY_COLORS["secondary_cyan"], bg_surf.get_rect(), 4, border_radius=18)
            
            surface.blit(bg_surf, bg_rect.topleft)
            surface.blit(txt_surf, (bg_rect.x + 40, bg_rect.y + 12))

    def _draw_hint(self, text):
        """在状态栏位置显示选择提示。"""
        self.status_msg = text
        self.status_timer = 120

    def _draw_discard_pile_dialog(self, surface, sel):
        """弃牌堆选择弹窗（马卡龙风格）。"""
        pg = pygame
        card_w, card_h = 70, 100
        gap = 16
        total = len(sel["options"])
        total_w = total * card_w + (total - 1) * gap
        
        # 绘制半透明黑色遮罩
        overlay = pg.Surface((self.manager.WIN_W, self.manager.WIN_H), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        surface.blit(overlay, (0, 0))
        
        # 弹窗背景板计算
        pw, ph = max(total_w + 80, 400), card_h + 140
        px = (self.manager.WIN_W - pw) // 2
        py = (self.manager.WIN_H - ph) // 2
        panel_rect = pg.Rect(px, py, pw, ph)
        
        # 绘制阴影和面板
        draw_drop_shadow(surface, panel_rect, radius=20, offset=(0, 10), alpha=60)
        draw_rounded_rect(surface, TOY_COLORS["panel_bg"], panel_rect, radius=20)
        pg.draw.rect(surface, TOY_COLORS["primary_yellow"], panel_rect, 4, border_radius=20)
        
        # 标题文字
        title_font = get_font(24, bold=True, style="chinese")
        title_txt = title_font.render("请选择要回收的卡牌", True, TOY_COLORS["dark_text"])
        surface.blit(title_txt, (px + (pw - title_txt.get_width()) // 2, py + 20))
        
        # 绘制候选卡牌
        start_x = px + (pw - total_w) // 2
        card_y = py + 80
        mx, my = pg.mouse.get_pos()
        
        for i, opt in enumerate(sel["options"]):
            rect = pg.Rect(start_x + i * (card_w + gap), card_y, card_w, card_h)
            is_hover = rect.collidepoint((mx, my))
            
            # 悬停弹起互动效果
            bg_color = (255, 255, 255) if not is_hover else (255, 250, 200)
            if is_hover:
                rect.y -= 6
                draw_drop_shadow(surface, rect, radius=10, offset=(0, 6), alpha=50)
            else:
                draw_drop_shadow(surface, rect, radius=10, offset=(0, 3), alpha=30)
                
            draw_rounded_rect(surface, bg_color, rect, radius=10)
            pg.draw.rect(surface, TOY_COLORS["secondary_cyan"] if is_hover else TOY_COLORS["panel_stroke"], rect, 2, border_radius=10)
            
            font = get_font(16, bold=True, style="chinese")
            name = opt.get("name", "?")
            txt = font.render(name, True, TOY_COLORS["dark_text"])
            surface.blit(txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2))

    def _draw_opponent_hand_highlight(self, surface):
        """封印对手手牌高亮（使用OPP_CARD常量+呼吸灯）。"""
        opp_color = "blue" if self.game.current_player_color == "red" else "red"
        opp = getattr(self.game, opp_color, None)
        if opp is None: return
        n = len(opp.hand)
        if n == 0: return
        
        cw, ch, gap = OPP_CARD_W, OPP_CARD_H, OPP_CARD_GAP
        total_w = n * cw + (n - 1) * gap
        start_x = self.manager.WIN_W - total_w - 20
        y = OPP_CARD_Y
        
        pulse = int(4 * math.sin(pygame.time.get_ticks() * 0.005))
        for i in range(n):
            rect = pygame.Rect(start_x + i * (cw + gap), y, cw, ch)
            hl_rect = rect.inflate(8 + pulse, 8 + pulse)
            pygame.draw.rect(surface, (255, 100, 100), hl_rect, 4, border_radius=12)
            pygame.draw.rect(surface, (255, 255, 255), hl_rect.inflate(4, 4), 2, border_radius=14)




    def _draw_tooltip(self, surface):
        if self.tooltip_timer > 0 and self.tooltip_text:
            if '\n' in self.tooltip_text:
                lines = self.tooltip_text.split('\n')
                font = get_font(16, style="chinese")
                max_w = max(font.size(line)[0] for line in lines)
                line_h = font.get_linesize() + 6
                bg_rect = pygame.Rect(self.tooltip_pos[0], self.tooltip_pos[1], max_w + 24, len(lines)*line_h + 16)
                
                if bg_rect.right > self.manager.WIN_W:
                    bg_rect.x = self.manager.WIN_W - bg_rect.w - 5
                if bg_rect.bottom > self.manager.WIN_H:
                    bg_rect.y = self.manager.WIN_H - bg_rect.h - 5
                    
                bg_surf = pygame.Surface((bg_rect.w, bg_rect.h), pygame.SRCALPHA)
                draw_rounded_rect(bg_surf, (*TOY_COLORS["panel_bg"][:3], 240), bg_surf.get_rect(), radius=10)
                pygame.draw.rect(bg_surf, TOY_COLORS["panel_stroke"], bg_surf.get_rect(), 2, border_radius=10)
                draw_drop_shadow(surface, bg_rect, radius=10, offset=(0, 4), alpha=40)
                surface.blit(bg_surf, bg_rect.topleft)
                
                for i, line in enumerate(lines):
                    color = TOY_COLORS["dark_text"]
                    if line.startswith("技能"): color = TOY_COLORS["accent_coral"]
                    elif line.startswith("【"): color = TOY_COLORS["secondary_cyan"]
                    txt_surf = font.render(line, True, color)
                    surface.blit(txt_surf, (bg_rect.x + 12, bg_rect.y + 10 + i * line_h))
            else:
                font = get_font(16, style="chinese")
                txt_surf = font.render(self.tooltip_text, True, TOY_COLORS["dark_text"])
                bg_rect = pygame.Rect(self.tooltip_pos[0], self.tooltip_pos[1], txt_surf.get_width() + 20, txt_surf.get_height() + 12)
                
                if bg_rect.right > self.manager.WIN_W: bg_rect.x = self.manager.WIN_W - bg_rect.w - 5
                if bg_rect.bottom > self.manager.WIN_H: bg_rect.y = self.manager.WIN_H - bg_rect.h - 5
                
                bg_surf = pygame.Surface((bg_rect.w, bg_rect.h), pygame.SRCALPHA)
                draw_rounded_rect(bg_surf, (*TOY_COLORS["panel_bg"][:3], 240), bg_surf.get_rect(), radius=8)
                pygame.draw.rect(bg_surf, TOY_COLORS["panel_stroke"], bg_surf.get_rect(), 2, border_radius=8)
                draw_drop_shadow(surface, bg_rect, radius=10, offset=(0, 4), alpha=40)
                surface.blit(bg_surf, bg_rect.topleft)
                surface.blit(txt_surf, (bg_rect.x + 10, bg_rect.y + 6))

    def _make_shadow_surface(self, half_size):
        size = (half_size + 8) * 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = size // 2
        shadow_rect = pygame.Rect(center - half_size - 2, center - half_size - 2, (half_size + 2) * 2, (half_size + 2) * 2)
        pygame.draw.rect(surf, (0, 0, 0, 40), shadow_rect, border_radius=TILE_ROUND_RADIUS + 2)
        return surf

    def _make_highlight_surface(self, half_size):
        size = half_size * 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        hl_rect = pygame.Rect(half_size // 3, half_size // 3, half_size, half_size)
        pygame.draw.rect(surf, (255, 255, 255, 35), hl_rect, border_radius=TILE_ROUND_RADIUS)
        return surf

    def _rebuild_bg_cache(self):
        self.bg_cache = build_board_background(self.manager.WIN_W,
                                               self.manager.WIN_H)
        tile_blit_grid(self.bg_cache, self._grid_tile_surf)
        # 区域淡色填充（在道路之下）
        draw_area_tints(self.bg_cache, self.game.board, self.camera)
        self._draw_roads(self.bg_cache)
        self._draw_area_bounds(self.bg_cache)
        self._draw_terrain_base(self.bg_cache)
        self.bg_dirty = False

    def _draw_roads(self, surface):
        board = self.game.board
        t = self.camera
        for u in board.adj:
            un = board.get_node(u)
            if un is None: continue
            sx1, sy1 = t.world_to_screen(un.x, un.y)
            for v in board.adj[u]:
                if v <= u: continue
                vn = board.get_node(v)
                if vn is None: continue
                sx2, sy2 = t.world_to_screen(vn.x, vn.y)
                start = pygame.Vector2(sx1, sy1)
                end = pygame.Vector2(sx2, sy2)
                dist = (end - start).length()
                if dist < t.apply_to_size(NODE_RENDER_RADIUS) * 2.5: continue
                dir_vec = (end - start).normalize()
                shrink_u = t.apply_to_size(NODE_RENDER_RADIUS + 2)
                if un.is_hq: shrink_u += t.apply_to_size(8)
                shrink_v = t.apply_to_size(NODE_RENDER_RADIUS + 2)
                if vn.is_hq: shrink_v += t.apply_to_size(8)
                start_edge = start + dir_vec * shrink_u
                end_edge = end - dir_vec * shrink_v
                road_width = max(4, int(8 * t.scale))
                draw_toy_plastic_road(surface, (int(start_edge.x), int(start_edge.y)), (int(end_edge.x), int(end_edge.y)), ROAD_COLOR, width=road_width)

    def _draw_terrain_base(self, surface):
        board = self.game.board
        t = self.camera
        nr = t.scaled_radius(NODE_RENDER_RADIUS)
        nr_hq = nr + max(1, int(4 * t.scale))
        shadow_normal = self._make_shadow_surface(nr)
        shadow_hq = self._make_shadow_surface(nr_hq)
        highlight_surf = self._make_highlight_surface(nr)

        for nid, nd in board.nodes.items():
            sx, sy = t.world_to_screen(nd.x, nd.y)
            x, y = int(sx), int(sy)
            terrain_color = TERRAIN_COLOR.get(nd.terrain_key, FALLBACK_GRAY)
            half = nr_hq if nd.is_hq else nr
            shadow = shadow_hq if nd.is_hq else shadow_normal
            shadow_offset = max(1, int(3 * t.scale))
            shadow_rect = shadow.get_rect(center=(x + shadow_offset, y + shadow_offset))
            surface.blit(shadow, shadow_rect)
            tile_rect = pygame.Rect(x - half, y - half, half * 2, half * 2)
            pygame.draw.rect(surface, terrain_color, tile_rect, border_radius=TILE_ROUND_RADIUS)
            border_color = get_border_color(nd.terrain_key)
            border_w = max(2, int(4 * t.scale))
            pygame.draw.rect(surface, border_color, tile_rect, border_w, border_radius=TILE_ROUND_RADIUS)
            # HQ 双边框 + 旗帜
            if nd.is_hq:
                outer_rect = tile_rect.inflate(8, 8)
                pygame.draw.rect(surface, border_color, outer_rect, 2, border_radius=TILE_ROUND_RADIUS)
                # 旗杆 + 三角旗
                flag_h = max(6, int(14 * t.scale))
                pole_x = x + half - 2
                pole_top = y - half - flag_h
                pygame.draw.line(surface, (100, 100, 100),
                                 (pole_x, y - half), (pole_x, pole_top), 2)
                flag_pts = [(pole_x, pole_top),
                            (pole_x + max(4, int(10 * t.scale)), pole_top + flag_h // 2),
                            (pole_x, pole_top + flag_h // 2)]
                hq_flag_color = PLAYER_COLORS.get(nd.hq_owner, border_color)
                pygame.draw.polygon(surface, hq_flag_color, flag_pts)
            hl_rect = highlight_surf.get_rect(center=(x, y))
            surface.blit(highlight_surf, hl_rect)

    def _draw_terrain_icons(self, surface):
        board = self.game.board
        t = self.camera
        nr = t.scaled_radius(NODE_RENDER_RADIUS)
        nr_hq = nr + max(1, int(4 * t.scale))
        for nid, nd in board.nodes.items():
            sx, sy = t.world_to_screen(nd.x, nd.y)
            x, y = int(sx), int(sy)
            half = nr_hq if nd.is_hq else nr
            inner_half = half - int(TILE_PADDING * t.scale)
            ter_size = max(4, int(inner_half * 1.4))
            ter_surf = get_cached_terrain(nd.terrain_key, target_size=ter_size)
            surface.blit(ter_surf, (x - ter_surf.get_width() // 2, y - ter_surf.get_height() // 2))

    def _draw_terrain_status(self, surface):
        """地形状态覆盖：泥沼禁止符号 + 金属X站标记。"""
        board = self.game.board
        t = self.camera
        nr = t.scaled_radius(NODE_RENDER_RADIUS)
        nr_hq = nr + max(1, int(4 * t.scale))
        for nid, nd in board.nodes.items():
            sx, sy = t.world_to_screen(nd.x, nd.y)
            x, y = int(sx), int(sy)
            half = nr_hq if nd.is_hq else nr
            # 泥沼禁止符号
            if nd.terrain_key == "mud":
                ban_r = max(4, int(half * 0.35))
                pygame.draw.circle(surface, (220, 50, 50), (x, y), ban_r, max(2, int(3 * t.scale)))
                lw = max(1, int(2 * t.scale))
                pygame.draw.line(surface, (220, 50, 50),
                                 (x - ban_r + 2, y - ban_r + 2),
                                 (x + ban_r - 2, y + ban_r - 2), lw)
            # 金属X站标记
            if nd.terrain_key == "metal_station":
                x_r = max(4, int(half * 0.3))
                lw = max(1, int(2 * t.scale))
                pygame.draw.line(surface, (180, 180, 180),
                                 (x - x_r, y - x_r), (x + x_r, y + x_r), lw)
                pygame.draw.line(surface, (180, 180, 180),
                                 (x + x_r, y - x_r), (x - x_r, y + x_r), lw)

    def _draw_board(self, surface):
        if self.bg_dirty or self.bg_cache is None:
            self._rebuild_bg_cache()
        surface.blit(self.bg_cache, (0, 0))

        board = self.game.board
        t = self.camera
        valid_set = set(nd.nid for nd in self.valid_nodes)
        nr = t.scaled_radius(NODE_RENDER_RADIUS)
        nr_hq = nr + max(1, int(4 * t.scale))

        self._draw_faction_overlay(surface, nr, nr_hq)

        for nid, node in board.nodes.items():
            if node.is_hq:
                sx, sy = t.world_to_screen(node.x, node.y)
                x, y = int(sx), int(sy)
                half = nr_hq
                hq_color = PLAYER_COLORS.get(node.hq_owner, FALLBACK_GRAY)
                alpha = int(128 + 64 * math.sin(pygame.time.get_ticks() * 0.005))
                ring_surf = pygame.Surface((half * 2 + 10, half * 2 + 10), pygame.SRCALPHA)
                center = half + 5
                ring_rect = pygame.Rect(center - half - 3, center - half - 3, (half + 3) * 2, (half + 3) * 2)
                ring_w = max(2, int(4 * t.scale))
                pygame.draw.rect(ring_surf, (*hq_color, alpha), ring_rect, ring_w, border_radius=TILE_ROUND_RADIUS + 3)
                surface.blit(ring_surf, (x - center, y - center))

        pending = getattr(self.game, 'pending_skill', None)
        if pending:
            src_node = board.get_node(pending["source_nid"])
            src_sx, src_sy = (0, 0)
            if src_node:
                src_sx, src_sy = t.world_to_screen(src_node.x, src_node.y)

            if self.skill_target_nodes:
                pulse_alpha = int(160 + 80 * math.sin(self.skill_pulse_time * 4.0))
                pulse_expand = int(4 * math.sin(self.skill_pulse_time * 4.0))
                for nd in self.skill_target_nodes:
                    sx, sy = t.world_to_screen(nd.x, nd.y)
                    x, y = int(sx), int(sy)
                    half = nr_hq if nd.is_hq else nr
                    skill_half = half + max(2, int(6 * t.scale)) + pulse_expand
                    skill_surf = pygame.Surface((skill_half * 2 + 6, skill_half * 2 + 6), pygame.SRCALPHA)
                    center = skill_half + 3
                    skill_rect = pygame.Rect(center - skill_half, center - skill_half, skill_half * 2, skill_half * 2)
                    skill_w = max(3, int(5 * t.scale))
                    pygame.draw.rect(skill_surf, (255, 50, 50, pulse_alpha), skill_rect, skill_w, border_radius=TILE_ROUND_RADIUS + 2)
                    surface.blit(skill_surf, (x - center, y - center))

            if self.hover_node and src_node and self.hover_node in self.skill_target_nodes:
                tgt_sx, tgt_sy = t.world_to_screen(self.hover_node.x, self.hover_node.y)
                line_w = max(2, int(5 * t.scale * self.placement_pulse_scale))
                laser_alpha = int(180 + 60 * math.sin(self.skill_pulse_time * 4.0))
                laser_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
                pygame.draw.line(laser_surf, (255, 80, 80, laser_alpha), (int(src_sx), int(src_sy)), (int(tgt_sx), int(tgt_sy)), line_w)
                surface.blit(laser_surf, (0, 0))
                mid_x = int((src_sx + tgt_sx) / 2)
                mid_y = int((src_sy + tgt_sy) / 2)
                glow_r = max(4, int(8 * t.scale))
                pygame.draw.circle(surface, (255, 200, 200), (mid_x, mid_y), glow_r)

            if self.skill_target_nodes:
                p_text = "请点击高亮节点释放技能"
                sub_text = "[ 右键 或 ESC 强制跳过 ]"
                theme_color = TOY_COLORS["accent_coral"]
            else:
                p_text = "警告：技能无有效目标"
                sub_text = "[ 请按 右键 或 ESC 强制跳过 ]"
                theme_color = TOY_COLORS["danger_red"]

            font_main = get_font(32, bold=True, style="chinese")
            font_sub = get_font(20, bold=True, style="chinese")

            surf_main = font_main.render(p_text, True, TOY_COLORS["dark_text"])
            surf_sub = font_sub.render(sub_text, True, (100, 100, 100))

            pw = max(surf_main.get_width(), surf_sub.get_width()) + 100
            ph = 110
            px = self.manager.WIN_W // 2 - pw // 2
            py = 20  

            prompt_panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
            draw_rounded_rect(prompt_panel, (255, 250, 240, 245), prompt_panel.get_rect(), radius=20)
            pygame.draw.rect(prompt_panel, theme_color, prompt_panel.get_rect(), 6, border_radius=20)

            surface.blit(prompt_panel, (px, py))
            surface.blit(surf_main, (px + pw//2 - surf_main.get_width()//2, py + 18))
            surface.blit(surf_sub, (px + pw//2 - surf_sub.get_width()//2, py + 65))

        elif valid_set:
            for nid in valid_set:
                node = board.get_node(nid)
                if node is None: continue
                sx, sy = t.world_to_screen(node.x, node.y)
                x, y = int(sx), int(sy)
                half = nr_hq if node.is_hq else nr
                pulse_half = int(half * self.placement_pulse_scale) + max(2, int(6 * t.scale))
                glow_color = lighten_color(PLAYER_COLORS[self.game.current_player_color], 60)
                glow_surf = pygame.Surface((pulse_half * 2 + 4, pulse_half * 2 + 4), pygame.SRCALPHA)
                center = pulse_half + 2
                glow_w = max(2, int(4 * t.scale))
                glow_rect = pygame.Rect(center - pulse_half, center - pulse_half, pulse_half * 2, pulse_half * 2)
                pygame.draw.rect(glow_surf, (*glow_color, 160), glow_rect, glow_w, border_radius=TILE_ROUND_RADIUS)
                surface.blit(glow_surf, (x - center, y - center))

        self._draw_hover_highlight(surface, nr, nr_hq)
        self._draw_terrain_icons(surface)
        self._draw_terrain_status(surface)
        self._draw_all_stars(surface)
        self._draw_garrison(surface, nr, nr_hq)

    def _draw_faction_overlay(self, surface, nr, nr_hq):
        board = self.game.board
        t = self.camera
        for nid, node in board.nodes.items():
            if not node.top_troop: continue
            sx, sy = t.world_to_screen(node.x, node.y)
            x, y = int(sx), int(sy)
            half = nr_hq if node.is_hq else nr
            owner_color = PLAYER_COLORS.get(node.top_troop.owner, FALLBACK_GRAY)
            tile_rect = pygame.Rect(x - half, y - half, half * 2, half * 2)
            draw_alpha_rect(surface, (*owner_color, FACTION_BG_ALPHA), tile_rect, radius=TILE_ROUND_RADIUS)

    def _draw_hover_highlight(self, surface, nr, nr_hq):
        if self.hover_node is None or self.hover_alpha < 10: return
        t = self.camera
        nd = self.hover_node
        sx, sy = t.world_to_screen(nd.x, nd.y)
        x, y = int(sx), int(sy)
        half = nr_hq if nd.is_hq else nr
        tile_rect = pygame.Rect(x - half, y - half, half * 2, half * 2)
        hover_surf = pygame.Surface((half * 2, half * 2), pygame.SRCALPHA)
        border_w = max(2, int(3 * t.scale))
        alpha = int(self.hover_alpha * 0.6)
        pygame.draw.rect(hover_surf, (*BORDER_HOVER, alpha), hover_surf.get_rect(), border_w, border_radius=TILE_ROUND_RADIUS)
        surface.blit(hover_surf, tile_rect.topleft)

    def _draw_garrison(self, surface, nr, nr_hq):
        board = self.game.board
        t = self.camera
        for nid, node in board.nodes.items():
            if not node.top_troop: continue
            sx, sy = t.world_to_screen(node.x, node.y)
            x, y = int(sx), int(sy)
            half = nr_hq if node.is_hq else nr
            troop = node.top_troop
            owner_color = PLAYER_COLORS.get(troop.owner, FALLBACK_GRAY)
            base_half = half - max(2, int(8 * t.scale))
            base_rect = pygame.Rect(x - base_half, y - base_half, base_half * 2, base_half * 2)
            bg_surf = pygame.Surface((base_half * 2, base_half * 2), pygame.SRCALPHA)
            pygame.draw.rect(bg_surf, (*owner_color, TEAM_BG_ALPHA), bg_surf.get_rect(), border_radius=TILE_ROUND_RADIUS)
            surface.blit(bg_surf, base_rect.topleft)
            base_w = max(1, int(2 * t.scale))
            pygame.draw.rect(surface, BORDER_WHITE, base_rect, base_w, border_radius=TILE_ROUND_RADIUS)
            tro_surf = get_cached_troop(troop.troop_key, troop.owner, target_size=int(base_half * 1.6))
            surface.blit(tro_surf, (x - tro_surf.get_width() // 2, y - tro_surf.get_height() // 2))
            # 堆叠数量角标
            stack_count = len(node.stack) if hasattr(node, "stack") and node.stack else 1
            if stack_count > 1:
                badge_r = max(8, int(10 * t.scale))
                bx = x + base_half - badge_r // 2
                by = y - base_half + badge_r // 2
                pygame.draw.circle(surface, TOY_COLORS["accent_coral"], (bx, by), badge_r)
                pygame.draw.circle(surface, (255, 255, 255), (bx, by), badge_r, 1)
                cnt_font = get_font(max(10, int(12 * t.scale)), bold=True)
                cnt_surf = cnt_font.render(str(stack_count), True, (255, 255, 255))
                surface.blit(cnt_surf, (bx - cnt_surf.get_width() // 2,
                                        by - cnt_surf.get_height() // 2))

    def _draw_hover_panel(self, surface):
        if self.hover_alpha < 10 or self.hover_node is None:
            return
        nd = self.hover_node
        ter = TERRAIN_DATA.get(nd.terrain_key, {})
        
        panel_w = 320
        panel_h = 100
        if nd.stack:
            panel_h += 30 + len(nd.stack) * 24
            
        panel_x = self.manager.WIN_W - panel_w - 20
        panel_y = self.manager.WIN_H - panel_h - 100
        
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        alpha = int(self.hover_alpha * 0.92)
        panel_surf.fill((*TOY_COLORS["panel_bg"][:3], alpha))
        pygame.draw.rect(panel_surf, (*TOY_COLORS["panel_stroke"], alpha),
                         panel_surf.get_rect(), 3, border_radius=14)
        surface.blit(panel_surf, (panel_x, panel_y))
        
        name_font = get_font(22, bold=True, style="chinese")
        name = ter.get("name", nd.terrain_key)
        name_surf = name_font.render(name, True, TOY_COLORS["dark_text"])
        title_x = panel_x + 14
        surface.blit(name_surf, (title_x, panel_y + 12))
        
        font_desc = get_font(16, style="chinese")
        desc = ter.get("desc", "")
        line_h, max_chars = 22, 18
        y_off = panel_y + 44
        
        for i in range(0, len(desc), max_chars):
            line = desc[i:i + max_chars]
            desc_surf = font_desc.render(line, True, (80, 80, 80))
            surface.blit(desc_surf, (panel_x + 14, y_off))
            y_off += line_h
            
        if nd.stack:
            pygame.draw.line(surface, (200, 200, 200), (panel_x + 10, y_off + 4), (panel_x + panel_w - 10, y_off + 4))
            y_off += 14
            
            stack_title = get_font(16, bold=True, style="chinese").render("当前地块堆叠列表 (从上到下):", True, TOY_COLORS["dark_text"])
            surface.blit(stack_title, (panel_x + 14, y_off))
            y_off += 24
            
            for idx, tp in enumerate(reversed(nd.stack)):
                layer_txt = "顶层" if idx == 0 else f"第{len(nd.stack)-idx}层"
                t_name = f"[{layer_txt}] {tp.name} (战力:{tp.number or 'J'})"
                t_name_surf = get_font(16, bold=True, style="chinese").render(t_name, True, PLAYER_COLORS.get(tp.owner, (0,0,0)))
                surface.blit(t_name_surf, (panel_x + 14, y_off))
                y_off += 24

    def _draw_area_bounds(self, surface):
        board = self.game.board
        if not board.nodes: return
        t = self.camera
        area_nodes = {}
        for nid, node in board.nodes.items():
            aid = node.area_id
            area_nodes.setdefault(aid, []).append(node)
        if not area_nodes: return
        for aid, nodes_in_area in area_nodes.items():
            if len(nodes_in_area) < 2: continue
            xs = [t.world_to_screen(n.x, n.y)[0] for n in nodes_in_area]
            ys = [t.world_to_screen(n.x, n.y)[1] for n in nodes_in_area]
            pad = 18 * t.scale
            min_x = min(xs) - pad
            min_y = min(ys) - pad
            max_x = max(xs) + pad
            max_y = max(ys) + pad
            rect = pygame.Rect(int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))
            bg_color = AREA_BOUNDS_COLORS[aid % len(AREA_BOUNDS_COLORS)]
            border_color = darken_color(bg_color, 40)
            bg_alpha = (*bg_color, 20)
            stroke_alpha = (*border_color, 90)
            bounds_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            draw_rounded_rect(bounds_surf, bg_alpha, bounds_surf.get_rect(topleft=(0, 0)), radius=12, stroke_width=1, stroke_color=stroke_alpha)
            surface.blit(bounds_surf, rect.topleft)

    def _draw_all_stars(self, surface):
        board = self.game.board
        star_points = board.star_points
        if not star_points: return
        t = self.camera
        star_size = max(8, int(14 * t.scale * 0.65))
        area_node_map = {}
        for nid, nd in board.nodes.items():
            area_node_map.setdefault(nd.area_id, []).append(nd)

        for sp in star_points:
            if not sp.get("has_star", True): continue
            aid = sp.get("area_id", -1)
            wx, wy = sp["x"], sp["y"]
            nodes_in_area = area_node_map.get(aid, [])
            if len(nodes_in_area) >= 2:
                xs = [n.x for n in nodes_in_area]
                ys = [n.y for n in nodes_in_area]
                cx = (min(xs) + max(xs)) / 2
                cy = (min(ys) + max(ys)) / 2
                offset_x = (max(xs) - min(xs)) * 0.12
                offset_y = (max(ys) - min(ys)) * 0.12
                wx = max(min(wx, cx + offset_x), cx - offset_x) if offset_x > 0 else cx
                wy = max(min(wy, cy + offset_y), cy - offset_y) if offset_y > 0 else cy

            sx, sy = t.world_to_screen(wx, wy)
            cx, cy = int(sx), int(sy)
            if aid in self.game.red.captured_areas:
                star_surf = get_cached_star("red", star_size)
            elif aid in self.game.blue.captured_areas:
                star_surf = get_cached_star("blue", star_size)
            else:
                star_surf = get_cached_star("gray", star_size)
            trans_surf = star_surf.copy()
            trans_surf.set_alpha(190)
            surface.blit(trans_surf, (cx - star_surf.get_width() // 2, cy - star_surf.get_height() // 2))