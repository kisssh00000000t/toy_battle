"""
战报大厅二级界面 — 浏览与播放历史战报。

独立 Screen 场景，通过 manager.switch_to 切换，
扫描 replays/ 目录中的 JSON 战报文件，提供卡片式选择。
"""

import json
import logging
from pathlib import Path

import pygame

from .base_screen import BaseScreen, play_stagger_spawn
from .widgets import ToyButton, ToyLabel, ToyPanel, ToyTitle, TOY_COLORS, get_font

logger = logging.getLogger(__name__)

# replays 目录路径（项目根目录下）
REPLAYS_DIR = Path(__file__).parent.parent / "replays"


class _ReplayCard:
    """战报卡片：显示文件名、时间、玩家信息。"""

    def __init__(self, x, y, w, h, replay_file: Path, callback):
        self.rect = pygame.Rect(x, y, w, h)
        self.replay_file = replay_file
        self.callback = callback
        self.hover = False
        self.alpha = 255

        # 解析元数据
        self.meta = self._parse_meta()
        self.label_name = self.meta.get("name", replay_file.stem)
        winner = self.meta.get("winner", "?")
        turns = self.meta.get("turns", 0)
        self.info_text = f"胜者: {winner} | 回合数: {turns}"

    def _parse_meta(self) -> dict:
        """从 JSON 战报文件中提取元数据。"""
        try:
            with open(self.replay_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            winner = data.get("winner", "未知")
            action_log = data.get("action_log", [])
            return {
                "name": self.replay_file.stem,
                "winner": winner if winner else "未结束",
                "turns": len(action_log),
                "data": data,
            }
        except Exception as e:
            logger.warning(f"解析战报 {self.replay_file.name} 失败: {e}")
            return {"name": self.replay_file.stem, "winner": "?", "turns": 0}

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.rect.collidepoint(event.pos) and self.callback:
                self.callback(self.replay_file)

    def draw(self, surface):
        bg = TOY_COLORS["panel_bg"] if not self.hover else lighten_card_bg()
        tmp = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(tmp, bg, (0, 0, *self.rect.size), border_radius=10)
        pygame.draw.rect(tmp, TOY_COLORS["panel_stroke"],
                         (0, 0, *self.rect.size), width=2, border_radius=10)
        tmp.set_alpha(int(self.alpha))
        surface.blit(tmp, self.rect.topleft)

        # 卡片标题
        font_title = get_font(20, bold=True, style="chinese")
        title_surf = font_title.render(self.label_name, True, TOY_COLORS["dark_text"])
        surface.blit(title_surf, (self.rect.x + 16, self.rect.y + 10))

        # 卡片信息
        font_info = get_font(16, style="chinese")
        info_surf = font_info.render(self.info_text, True, TOY_COLORS["shadow"])
        surface.blit(info_surf, (self.rect.x + 16, self.rect.y + 38))

        # 播放指示
        if self.hover:
            font_play = get_font(14, bold=True, style="chinese")
            play_surf = font_play.render("\u25B6 点击观战", True, TOY_COLORS["secondary_cyan"])
            surface.blit(play_surf, (self.rect.right - 100, self.rect.y + 20))


def lighten_card_bg():
    """卡片悬浮时稍亮的背景色。"""
    return (255, 255, 245)


class ReplaySelectScreen(BaseScreen):
    """二级界面：战报大厅 — 浏览与播放历史战报。"""

    def __init__(self, manager):
        super().__init__(manager)

        # 1. 顶部标题
        self.title = ToyTitle(
            "战报大厅", center_x=manager.WIN_W // 2, center_y=90,
            font_size=64, base_color=TOY_COLORS["accent_coral"]
        )
        self.subtitle = ToyLabel(
            "Battle Replays", (manager.WIN_W // 2 - 100, 150),
            font_size=24, color=TOY_COLORS["dark_text"]
        )

        # 2. 返回按钮
        self.btn_back = ToyButton(
            "返回主菜单", rect=(40, 20, 180, 50),
            callback=self._go_back,
            color=TOY_COLORS["danger_red"], icon_type="back"
        )

        # 3. 刷新按钮
        self.btn_refresh = ToyButton(
            "刷新列表", rect=(manager.WIN_W - 390, 20, 150, 50),
            callback=self._refresh_list,
            color=TOY_COLORS["soft_blue"], icon_type="refresh"
        )
        # 4. 一键清空战报按钮（右上醒目红色）
        self.btn_clear_all = ToyButton(
            "\U0001F5D1 清空战报", rect=(manager.WIN_W - 220, 20, 180, 50),
            callback=self._clear_all_replays,
            color=TOY_COLORS["danger_red"], icon_type="clear"
        )

        # 5. 战报卡片列表
        self.cards: list[_ReplayCard] = []
        self._build_cards()

        # 5. 空状态提示
        self.empty_msg = ""

        # 6. 状态消息（清空战报等反馈）
        self.status_msg = ""
        self.status_timer = 0

        # 7. 滚动偏移
        self.scroll_y = 0
        self.max_scroll = 0

        self.widgets = [self.title, self.subtitle, self.btn_back, self.btn_refresh, self.btn_clear_all]

        # 进场动画
        play_stagger_spawn(self, anim_dur=0.3, gap=0.06, overlap_ratio=0.3)

    # ─── 卡片构建 ────────────────────────────────────────────

    def _build_cards(self):
        """扫描 replays/ 目录，构建战报卡片列表。"""
        self.cards.clear()
        REPLAYS_DIR.mkdir(parents=True, exist_ok=True)
        json_files = sorted(REPLAYS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime,
                            reverse=True)
        if not json_files:
            self.empty_msg = "暂无战报记录，请先进行一局对战"
            return
        self.empty_msg = ""

        card_w, card_h = 560, 70
        start_x = (self.manager.WIN_W - card_w) // 2
        start_y = 200
        gap = 12

        for i, jf in enumerate(json_files):
            cy = start_y + i * (card_h + gap)
            card = _ReplayCard(start_x, cy, card_w, card_h, jf, self._play_replay)
            self.cards.append(card)

        # 计算最大滚动
        total_h = len(self.cards) * (card_h + gap)
        visible_h = self.manager.WIN_H - start_y - 20
        self.max_scroll = max(0, total_h - visible_h)

    def _refresh_list(self):
        """刷新战报列表。"""
        self._build_cards()
        self.scroll_y = 0
        self._show_status("列表已刷新")

    def _clear_all_replays(self):
        """一键清空 replays/ 下所有 .json 战报文件。"""
        count = 0
        if REPLAYS_DIR.exists():
            for f in REPLAYS_DIR.glob("*.json"):
                try:
                    f.unlink()
                    count += 1
                except Exception as e:
                    logger.warning(f"删除战报 {f.name} 失败: {e}")
        self._build_cards()
        self.scroll_y = 0
        self._show_status(f"\u2713 已清空 {count} 条战报记录")

    def _show_status(self, msg: str):
        self.status_msg = msg
        self.status_timer = 120

    # ─── 回调 ────────────────────────────────────────────────

    def _go_back(self):
        from .menu_screen import MenuScreen
        self.manager.switch_to(MenuScreen)

    def _play_replay(self, replay_file: Path):
        """点击卡片，跳转到回放播放器。"""
        try:
            from .replay_screen import ReplayScreen
            self.manager.switch_to(ReplayScreen, replay_file=replay_file)
        except Exception as e:
            logger.error(f"无法进入观战播放器: {e}")

    # ─── 更新与绘制 ──────────────────────────────────────────

    def update(self, dt):
        self.title.update(dt)
        if self.status_timer > 0:
            self.status_timer -= 1

    def handle_event(self, event):
        super().handle_event(event)
        self.title.handle_event(event)
        # 滚轮滚动
        if event.type == pygame.MOUSEWHEEL:
            self.scroll_y -= event.y * 30
            self.scroll_y = max(0, min(self.scroll_y, self.max_scroll))
        # 卡片事件
        for card in self.cards:
            card.handle_event(event)

    def draw(self, surface):
        surface.fill(TOY_COLORS["bg_cream"])
        self.title.draw(surface)
        self.subtitle.draw(surface)
        self.btn_back.draw(surface)
        self.btn_refresh.draw(surface)
        self.btn_clear_all.draw(surface)

        # 状态消息反馈（清空战报等）
        if self.status_timer > 0 and self.status_msg:
            font = get_font(18, style="chinese")
            s_surf = font.render(self.status_msg, True, TOY_COLORS["success_green"])
            surface.blit(s_surf, ((self.manager.WIN_W - s_surf.get_width()) // 2, 160))

        if self.empty_msg:
            font = get_font(28, bold=True, style="chinese")
            msg_surf = font.render(self.empty_msg, True, TOY_COLORS["shadow"])
            surface.blit(msg_surf, ((self.manager.WIN_W - msg_surf.get_width()) // 2, 350))
            return

        # 裁剪区域绘制卡片（支持滚动）
        clip_rect = pygame.Rect(0, 190, self.manager.WIN_W, self.manager.WIN_H - 210)
        surface.set_clip(clip_rect)
        for card in self.cards:
            # 应用滚动偏移
            orig_y = card.rect.y
            card.rect.y -= self.scroll_y
            card.draw(surface)
            card.rect.y = orig_y
        surface.set_clip(None)