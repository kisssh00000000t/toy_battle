"""
Pygame 游戏主界面（改进版）。

修复：
- get_hand_troop 添加 self 参数
- 添加可放置节点高亮
- 手牌详情 tooltip
- 游戏结束"再来一局"按钮
- 回合指示器增强
- 操作反馈提示

改进：
- 前后端分离：UI 层不直接修改游戏状态
- 状态机驱动界面切换
- 动画效果基础框架
"""

import sys
import math
import logging
from pathlib import Path
from typing import Optional

import pygame

from .game.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    TERRAIN_COLOR, TROOP_COLOR,
    BG_COLOR, RED, BLUE,
    TILE_SQUARE_SIZE, TILE_ROUND_RADIUS, TILE_PADDING,
    HAND_CARD_W, HAND_CARD_H, HAND_Y,
)
from .game.game_logic import GameState
from .game.board import GameBoard
from .game.troop import Troop
from .game.map_loader import load_map

logger = logging.getLogger(__name__)

# 界面状态
STATE_MENU = "menu"
STATE_PLAYING = "playing"
STATE_GAME_OVER = "game_over"


class PygameApp:
    """游戏主界面。

    Attributes:
        screen: Pygame 显示表面
        clock: 帧率控制器
        game: 游戏状态实例（GameState）
        board: 棋盘实例
        state: 当前界面状态
        selected_troop: 当前选中的手牌索引
        valid_nodes: 当前可放置节点 ID 集合
        hover_card: 悬停的手牌索引
        hover_node: 悬停的节点 ID
        message: 操作反馈消息
        message_timer: 消息显示计时器
    """

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("玩具大乱斗")
        _icon_path = Path(__file__).parent.parent / "icon.png"
        if _icon_path.exists():
            pygame.display.set_icon(pygame.image.load(str(_icon_path)))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("simhei", 16)
        self.font_large = pygame.font.SysFont("simhei", 28)
        self.font_title = pygame.font.SysFont("simhei", 48)

        # 游戏状态
        self.game: Optional[GameState] = None
        self.board: Optional[GameBoard] = None
        self.state = STATE_MENU
        self.selected_troop: int = -1
        self.valid_nodes: set[int] = set()
        self.hover_card: int = -1
        self.hover_node: Optional[int] = None
        self.message: str = ""
        self.message_timer: int = 0
        self.tooltip_text: str = ""
        self.tooltip_pos: tuple[int, int] = (0, 0)

        # 按钮区域
        self.btn_start = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 - 30, 200, 60)
        self.btn_restart = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 50, 200, 60)
        self.btn_draw = pygame.Rect(SCREEN_WIDTH - 160, HAND_Y - 50, 140, 40)
        self.btn_end_turn = pygame.Rect(SCREEN_WIDTH - 160, HAND_Y - 100, 140, 40)

    def start_game(self) -> None:
        """初始化新游戏。"""
        map_data = load_map()
        self.board = GameBoard()
        self.board.load_from_dict(map_data)
        self.game = GameState()
        self.game.board = self.board
        self.game.setup()

        self.state = STATE_PLAYING
        self.selected_troop = -1
        self.valid_nodes = set()
        self.show_message("游戏开始！红方先手")

    def run(self) -> None:
        """主循环。"""
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.state == STATE_PLAYING:
                            self.state = STATE_MENU
                        else:
                            running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_click(event)
                elif event.type == pygame.MOUSEMOTION:
                    self._handle_motion(event)

            self._update()
            self._draw()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()

    def _handle_click(self, event: pygame.event.Event) -> None:
        """处理鼠标点击。"""
        mx, my = event.pos

        if self.state == STATE_MENU:
            if self.btn_start.collidepoint(mx, my):
                self.start_game()

        elif self.state == STATE_PLAYING:
            if not self.game or not self.board:
                return

            # 抽卡按钮
            if self.btn_draw.collidepoint(mx, my):
                self._do_draw_cards()
                return

            # 结束回合按钮
            if self.btn_end_turn.collidepoint(mx, my):
                self._do_end_turn()
                return

            # 点击手牌
            card_idx = self._find_card(mx, my)
            if card_idx >= 0:
                self._select_troop(card_idx)
                return

            # 点击棋盘节点
            if self.selected_troop >= 0:
                node = self.board.get_node_by_pos(mx, my)
                if node is not None and node.nid in self.valid_nodes:
                    self._place_troop(node)
                elif node is not None:
                    self.show_message("无法放置到此节点")

        elif self.state == STATE_GAME_OVER:
            if self.btn_restart.collidepoint(mx, my):
                self.start_game()

    def _handle_motion(self, event: pygame.event.Event) -> None:
        """处理鼠标移动。"""
        mx, my = event.pos
        self.hover_card = self._find_card(mx, my)

        if self.board:
            node = self.board.get_node_by_pos(mx, my)
            self.hover_node = node.nid if node else None
        else:
            self.hover_node = None

        # 更新 tooltip
        if self.hover_card >= 0 and self.game:
            cp = self.game.current_player
            hand = cp.hand
            if 0 <= self.hover_card < len(hand):
                troop = hand[self.hover_card]
                self.tooltip_text = f"{troop.alias} ({troop.symbol} 战力:{troop.number or 'J'})"
                self.tooltip_pos = (mx + 15, my - 10)
            else:
                self.tooltip_text = ""
        elif self.hover_node is not None and self.game and self.board:
            node = self.board.get_node(self.hover_node)
            if node:
                terrain = node.terrain_key
                top = node.top_troop
                troop_info = f"{top.alias}({top.number})" if top else "空"
                owner_info = top.owner if top else "无"
                self.tooltip_text = f"节点{node.nid} | 地形:{terrain} | 占领:{owner_info} | 兵种:{troop_info}"
                self.tooltip_pos = (mx + 15, my - 10)
        else:
            self.tooltip_text = ""

    def _find_card(self, mx: int, my: int) -> int:
        """查找鼠标位置下的手牌索引。"""
        if not self.game:
            return -1
        cp = self.game.current_player
        hand = cp.hand
        start_x = 20
        for i in range(len(hand)):
            rect = pygame.Rect(start_x + i * (HAND_CARD_W + 10), HAND_Y, HAND_CARD_W, HAND_CARD_H)
            if rect.collidepoint(mx, my):
                return i
        return -1

    def _select_troop(self, card_idx: int) -> None:
        """选中手牌并计算可放置节点。"""
        if not self.game:
            return
        self.selected_troop = card_idx
        cp = self.game.current_player
        hand = cp.hand
        if 0 <= card_idx < len(hand):
            troop = hand[card_idx]
            valid_nodes = self.game.get_valid_nodes(troop)
            self.valid_nodes = {nd.nid for nd in valid_nodes}
            if not self.valid_nodes:
                self.show_message(f"{troop.alias} 没有可放置的位置")
            else:
                self.show_message(f"已选择 {troop.alias}，点击高亮节点放置")

    def _place_troop(self, node) -> None:
        """放置兵种到节点。"""
        if not self.game or self.selected_troop < 0:
            return
        cp = self.game.current_player
        hand = cp.hand
        if 0 <= self.selected_troop < len(hand):
            troop = hand[self.selected_troop]
            success = self.game.place_troop(troop, node)
            if success:
                self.show_message(f"放置 {troop.alias} 到节点 {node.nid}")
            else:
                self.show_message(f"放置失败: {self.game.turn_msg}")

        self.selected_troop = -1
        self.valid_nodes = set()

        # 检查游戏结束
        if self.game.game_over:
            self.state = STATE_GAME_OVER

    def _do_draw_cards(self) -> None:
        """执行抽卡。"""
        if not self.game:
            return
        ok, err = self.game.draw_cards_action()
        if ok:
            self.show_message(self.game.turn_msg)
        else:
            self.show_message(f"抽卡失败: {err}")

        if self.game.game_over:
            self.state = STATE_GAME_OVER

    def _do_end_turn(self) -> None:
        """结束当前回合。"""
        if not self.game:
            return
        self.game.end_turn()
        cp = self.game.current_player
        self.selected_troop = -1
        self.valid_nodes = set()
        self.show_message(f"回合切换: {cp.color}")

    def _update(self) -> None:
        """每帧更新。"""
        if self.message_timer > 0:
            self.message_timer -= 1

    def show_message(self, msg: str, duration: int = 120) -> None:
        """显示操作反馈消息。"""
        self.message = msg
        self.message_timer = duration

    def _draw(self) -> None:
        """绘制界面。"""
        self.screen.fill(BG_COLOR)

        if self.state == STATE_MENU:
            self._draw_menu()
        elif self.state == STATE_PLAYING:
            self._draw_game()
        elif self.state == STATE_GAME_OVER:
            self._draw_game_over()

        pygame.display.flip()

    def _draw_menu(self) -> None:
        """绘制主菜单。"""
        title = self.font_title.render("玩具大乱斗", True, (255, 215, 0))
        self.screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, SCREEN_HEIGHT // 3 - 40))

        mouse_pos = pygame.mouse.get_pos()
        color = (80, 180, 80) if self.btn_start.collidepoint(mouse_pos) else (60, 140, 60)
        pygame.draw.rect(self.screen, color, self.btn_start, border_radius=10)
        text = self.font_large.render("开始游戏", True, (255, 255, 255))
        self.screen.blit(text, (self.btn_start.centerx - text.get_width() // 2,
                                self.btn_start.centery - text.get_height() // 2))

    def _draw_game(self) -> None:
        """绘制游戏界面。"""
        if not self.game or not self.board:
            return

        # 绘制边
        for nid, neighbors in self.board.adj.items():
            for nb in neighbors:
                if nid < nb:  # 避免重复绘制
                    node_a = self.board.get_node(nid)
                    node_b = self.board.get_node(nb)
                    if node_a and node_b:
                        pygame.draw.line(self.screen, (120, 120, 120),
                                         (int(node_a.x), int(node_a.y)),
                                         (int(node_b.x), int(node_b.y)), 2)

        # 绘制节点
        for nid, node in self.board.nodes.items():
            terrain = node.terrain_key
            base_color = TERRAIN_COLOR.get(terrain, (100, 100, 100))

            # 可放置高亮
            is_valid = nid in self.valid_nodes
            is_hover = nid == self.hover_node

            # 绘制节点（圆角方形）
            half = TILE_SQUARE_SIZE // 2
            nx, ny = int(node.x), int(node.y)
            tile_rect = pygame.Rect(nx - half, ny - half,
                                    TILE_SQUARE_SIZE, TILE_SQUARE_SIZE)
            if is_valid:
                pulse = int(3 * math.sin(pygame.time.get_ticks() / 200))
                pulse_rect = tile_rect.inflate(pulse + 6, pulse + 6)
                pygame.draw.rect(self.screen, (255, 255, 100),
                                 pulse_rect, 3, border_radius=TILE_ROUND_RADIUS + 3)

            pygame.draw.rect(self.screen, base_color, tile_rect,
                             border_radius=TILE_ROUND_RADIUS)

            # 所有者边框
            top = node.top_troop
            if top:
                owner_color = RED if top.owner == "red" else BLUE
                pygame.draw.rect(self.screen, owner_color, tile_rect, 3,
                                 border_radius=TILE_ROUND_RADIUS)

            # HQ 标记
            if node.is_hq:
                hq_color = RED if node.hq_owner == "red" else BLUE
                pygame.draw.rect(self.screen, hq_color,
                                 tile_rect.inflate(10, 10), 2,
                                 border_radius=TILE_ROUND_RADIUS + 5)

            # 地形名称（替代emoji符号）
            ter_name = TERRAIN_DATA.get(terrain, {}).get("name", terrain)
            if ter_name:
                text = self.font.render(ter_name[:2], True, (0, 0, 0))
                self.screen.blit(text, (node.x - text.get_width() // 2,
                                        node.y - text.get_height() // 2))

            # 兵种战力
            if top:
                val_text = self.font.render(str(top.number or "J"), True, (255, 255, 255))
                self.screen.blit(val_text, (nx + half - 14, ny - half + 2))

            # 悬停高亮
            if is_hover:
                pygame.draw.rect(self.screen, (255, 255, 255),
                                 tile_rect.inflate(4, 4), 2,
                                 border_radius=TILE_ROUND_RADIUS + 2)

        # 绘制手牌区
        self._draw_hand()

        # 绘制回合信息
        self._draw_turn_info()

        # 绘制按钮
        self._draw_buttons()

        # 绘制 tooltip
        if self.tooltip_text:
            self._draw_tooltip()

        # 绘制消息
        if self.message_timer > 0:
            self._draw_message()

    def _draw_hand(self) -> None:
        """绘制当前玩家手牌。"""
        if not self.game:
            return
        cp = self.game.current_player
        hand = cp.hand
        start_x = 20

        for i, troop in enumerate(hand):
            x = start_x + i * (HAND_CARD_W + 10)
            y = HAND_Y
            rect = pygame.Rect(x, y, HAND_CARD_W, HAND_CARD_H)

            troop_color = TROOP_COLOR.get(troop.troop_key, (180, 180, 180))
            is_selected = i == self.selected_troop
            is_hover = i == self.hover_card

            if is_selected:
                pygame.draw.rect(self.screen, (255, 255, 100), rect.inflate(6, 6), border_radius=6)
            elif is_hover:
                pygame.draw.rect(self.screen, (200, 200, 200), rect.inflate(4, 4), border_radius=5)

            pygame.draw.rect(self.screen, troop_color, rect, border_radius=4)
            pygame.draw.rect(self.screen, (60, 60, 60), rect, 2, border_radius=4)

            # 兵种符号+名称
            sym_text = self.font.render(troop.alias, True, (0, 0, 0))
            self.screen.blit(sym_text, (x + 5, y + 5))
            name_text = self.font.render(troop.name, True, (0, 0, 0))
            self.screen.blit(name_text, (x + 5, y + 25))

            # 战力值
            val = str(troop.number) if troop.number else "J"
            val_text = self.font.render(f"战力:{val}", True, (40, 40, 40))
            self.screen.blit(val_text, (x + 5, y + 45))

    def _draw_turn_info(self) -> None:
        """绘制回合信息。"""
        if not self.game:
            return
        cp = self.game.current_player
        color = RED if cp.color == "red" else BLUE
        turn_text = f"{cp.color.upper()} 方回合 | {self.game.turn_msg}"
        text = self.font_large.render(turn_text, True, color)
        self.screen.blit(text, (10, 10))

        # 牌堆信息
        red_deck = len(self.game.red.reserve)
        blue_deck = len(self.game.blue.reserve)
        deck_text = f"红方备用堆:{red_deck} | 蓝方备用堆:{blue_deck}"
        dt = self.font.render(deck_text, True, (200, 200, 200))
        self.screen.blit(dt, (10, 45))

        # 星星信息
        star_text = f"红方:{self.game.red.star_points} | 蓝方:{self.game.blue.star_points} (目标:{self.game.star_win_goal})"
        mt = self.font.render(star_text, True, (200, 200, 200))
        self.screen.blit(mt, (10, 65))

    def _draw_buttons(self) -> None:
        """绘制操作按钮。"""
        mouse_pos = pygame.mouse.get_pos()

        # 抽卡按钮
        draw_color = (80, 130, 200) if self.btn_draw.collidepoint(mouse_pos) else (60, 100, 160)
        pygame.draw.rect(self.screen, draw_color, self.btn_draw, border_radius=6)
        draw_text = self.font.render("抽卡", True, (255, 255, 255))
        self.screen.blit(draw_text, (self.btn_draw.centerx - draw_text.get_width() // 2,
                                     self.btn_draw.centery - draw_text.get_height() // 2))

        # 结束回合按钮
        end_color = (200, 130, 80) if self.btn_end_turn.collidepoint(mouse_pos) else (160, 100, 60)
        pygame.draw.rect(self.screen, end_color, self.btn_end_turn, border_radius=6)
        end_text = self.font.render("结束回合", True, (255, 255, 255))
        self.screen.blit(end_text, (self.btn_end_turn.centerx - end_text.get_width() // 2,
                                    self.btn_end_turn.centery - end_text.get_height() // 2))

    def _draw_tooltip(self) -> None:
        """绘制 tooltip。"""
        text = self.font.render(self.tooltip_text, True, (255, 255, 255))
        bg_rect = text.get_rect(topleft=self.tooltip_pos)
        bg_rect.inflate_ip(10, 6)
        pygame.draw.rect(self.screen, (30, 30, 30), bg_rect, border_radius=4)
        pygame.draw.rect(self.screen, (100, 100, 100), bg_rect, 1, border_radius=4)
        self.screen.blit(text, (self.tooltip_pos[0] + 5, self.tooltip_pos[1] + 3))

    def _draw_message(self) -> None:
        """绘制操作反馈消息。"""
        text = self.font.render(self.message, True, (255, 255, 200))
        x = SCREEN_WIDTH // 2 - text.get_width() // 2
        y = HAND_Y - 30
        bg_rect = text.get_rect(topleft=(x - 5, y - 2))
        bg_rect.inflate_ip(10, 6)
        pygame.draw.rect(self.screen, (40, 40, 40), bg_rect, border_radius=4)
        self.screen.blit(text, (x, y))

    def _draw_game_over(self) -> None:
        """绘制游戏结束界面。"""
        # 半透明遮罩
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.set_alpha(150)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        if self.game and self.game.winner:
            color = RED if self.game.winner == "red" else BLUE
            text = self.font_title.render(f"{self.game.winner.upper()} 获胜！", True, color)
        else:
            text = self.font_title.render("游戏结束", True, (255, 255, 255))

        self.screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2,
                                SCREEN_HEIGHT // 3))

        # 再来一局按钮
        mouse_pos = pygame.mouse.get_pos()
        btn_color = (80, 180, 80) if self.btn_restart.collidepoint(mouse_pos) else (60, 140, 60)
        pygame.draw.rect(self.screen, btn_color, self.btn_restart, border_radius=10)
        restart_text = self.font_large.render("再来一局", True, (255, 255, 255))
        self.screen.blit(restart_text, (self.btn_restart.centerx - restart_text.get_width() // 2,
                                        self.btn_restart.centery - restart_text.get_height() // 2))

    def get_hand_troop(self, player_color: str, index: int) -> Optional[Troop]:
        """获取指定玩家手牌中的兵种。

        修复：添加 self 参数。

        Args:
            player_color: 玩家颜色
            index: 手牌索引

        Returns:
            Troop 对象或 None
        """
        if not self.game:
            return None
        player = self.game.red if player_color == "red" else self.game.blue
        hand = player.hand
        if 0 <= index < len(hand):
            return hand[index]
        return None