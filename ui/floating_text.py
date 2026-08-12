"""
浮动战斗文字系统。
支持上浮、淡出、描边，用于吃子/自毁/封印/星星等事件反馈。
"""
import pygame
from .widgets import get_font


class FloatingText:
    """单条浮动文字。"""

    def __init__(self, text, x, y, color=(255, 80, 80), font_size=24,
                 duration=1.2, rise_speed=50):
        self.text = text
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.font_size = font_size
        self.duration = duration
        self.elapsed = 0.0
        self.alive = True
        self.rise_speed = rise_speed

    def update(self, dt):
        self.elapsed += dt
        self.y -= self.rise_speed * dt
        if self.elapsed >= self.duration:
            self.alive = False

    def draw(self, surface):
        t = self.elapsed / self.duration
        # 前20%淡入，后30%淡出
        if t < 0.2:
            alpha = int(255 * t / 0.2)
        elif t > 0.7:
            alpha = int(255 * (1 - (t - 0.7) / 0.3))
        else:
            alpha = 255
        alpha = max(0, min(255, alpha))

        font = get_font(self.font_size, bold=True, style="chinese")
        txt = font.render(self.text, True, self.color)
        outline = font.render(self.text, True, (0, 0, 0))
        txt.set_alpha(alpha)
        outline.set_alpha(alpha)

        cx = int(self.x - txt.get_width() / 2)
        cy = int(self.y - txt.get_height() / 2)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (1, 1), (-1, 1), (1, -1)):
            surface.blit(outline, (cx + dx, cy + dy))
        surface.blit(txt, (cx, cy))


class FloatingTextManager:
    """浮动文字管理器。"""

    def __init__(self):
        self.texts = []

    def emit(self, text, x, y, color=(255, 80, 80), font_size=24,
             duration=1.2, rise_speed=50):
        self.texts.append(FloatingText(text, x, y, color, font_size,
                                       duration, rise_speed))

    def update(self, dt):
        for t in self.texts:
            t.update(dt)
        self.texts = [t for t in self.texts if t.alive]

    def draw(self, surface):
        for t in self.texts:
            t.draw(surface)

    def clear(self):
        self.texts.clear()