"""
回合切换横幅。
滑入→停留→滑出，带半透明背景条。
"""
import pygame
from .widgets import get_font, draw_rounded_rect


class TurnBanner:
    """回合切换横幅动画。"""

    def __init__(self):
        self.timer = 0.0
        self.duration = 1.8
        self.text = ""
        self.color = (255, 255, 255)
        self.sub_text = ""

    def show(self, text, color, sub_text=""):
        self.text = text
        self.color = color
        self.sub_text = sub_text
        self.timer = self.duration

    @property
    def active(self):
        return self.timer > 0

    def update(self, dt):
        if self.timer > 0:
            self.timer -= dt

    def draw(self, surface):
        if self.timer <= 0:
            return
        t = 1 - self.timer / self.duration
        # 阶段：0-0.15 滑入，0.15-0.75 停留，0.75-1 滑出
        if t < 0.15:
            p = t / 0.15
            offset = int((1 - p) * -300)
            alpha = int(255 * p)
        elif t > 0.8:
            p = (t - 0.8) / 0.2
            offset = int(p * 300)
            alpha = int(255 * (1 - p))
        else:
            offset = 0
            alpha = 255

        font = get_font(44, bold=True, style="chinese")
        txt = font.render(self.text, True, self.color)
        txt.set_alpha(alpha)

        cx = surface.get_width() // 2
        cy = surface.get_height() // 3 + offset

        pw = txt.get_width() + 100
        ph = txt.get_height() + 24
        if self.sub_text:
            ph += 28

        bg = pygame.Surface((pw, ph), pygame.SRCALPHA)
        draw_rounded_rect(bg, (30, 30, 45, int(alpha * 0.85)),
                          bg.get_rect(), radius=20)
        pygame.draw.rect(bg, (*self.color, alpha), bg.get_rect(),
                         4, border_radius=20)
        surface.blit(bg, (cx - pw // 2, cy - ph // 2))
        surface.blit(txt, (cx - txt.get_width() // 2,
                           cy - ph // 2 + 10))

        if self.sub_text:
            sub_font = get_font(20, style="chinese")
            sub = sub_font.render(self.sub_text, True, (220, 220, 220))
            sub.set_alpha(alpha)
            surface.blit(sub, (cx - sub.get_width() // 2,
                               cy - ph // 2 + ph - 30))