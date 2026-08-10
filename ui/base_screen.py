"""
所有界面的基类。

提供统一的事件分发、更新和绘制接口，界面管理器通过此协议切换页面。
"""

from .widgets import TOY_COLORS
from .tween_manager import TWEEN
from .easing import EASE_CUBIC_OUT


class BaseScreen:
    """界面基类，所有具体界面继承此类。

    Attributes:
        manager: ScreenManager 实例，用于切换页面
        widgets: 可交互控件列表，统一接收事件分发
    """

    def __init__(self, manager):
        self.manager = manager
        self.widgets = []

    def handle_event(self, event):
        """分发事件到所有控件。"""
        for widget in self.widgets:
            if hasattr(widget, "handle_event"):
                widget.handle_event(event)

    def update(self, dt):
        """每帧更新逻辑，dt 为时间增量（秒）。"""
        pass

    def draw(self, surface):
        """绘制界面。默认填充奶油色背景并绘制所有控件。"""
        surface.fill(TOY_COLORS["bg_cream"])
        for widget in self.widgets:
            widget.draw(surface)


def play_stagger_spawn(screen_or_container, anim_dur=0.3, gap=0.08, overlap_ratio=0.3):
    """为容器内所有带 alpha 属性的控件创建交错淡入动画。

    Args:
        screen_or_container: 具有 widgets 属性的界面或容器
        anim_dur: 单个动画时长（秒）
        gap: 每个控件启动间隔（秒）
        overlap_ratio: 重叠比例 (0~1)，值越大控件重叠越强，消除排队感
    """
    widgets = getattr(screen_or_container, "widgets", [])
    delay = 0.0
    overlap_time = anim_dur * overlap_ratio
    for widget in widgets:
        if hasattr(widget, "alpha"):
            widget.alpha = 0
            TWEEN.create_tween(widget, "alpha", 255, anim_dur, delay, EASE_CUBIC_OUT)
            delay += gap - overlap_time