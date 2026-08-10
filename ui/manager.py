"""
全局界面状态机管理器。

负责Pygame窗口创建、主循环、界面切换和事件分发。
"""

import pygame
from pathlib import Path

from .tween_manager import TWEEN


class ScreenManager:
    """界面管理器，驱动多界面状态机。

    Attributes:
        WIN_W / WIN_H: 窗口尺寸
        screen: Pygame显示表面
        clock: 帧率控制器
        current_screen: 当前活跃界面实例
        running: 主循环是否继续
    """

    WIN_W = 1280
    WIN_H = 800

    def __init__(self):
        self.screen = None
        self.clock = None
        self.current_screen = None
        self.running = False

    def switch_to(self, screen_class, **kwargs):
        """切换到指定界面类，支持传参。

        Args:
            screen_class: BaseScreen 子类
            **kwargs: 传递给界面构造函数的参数
        """
        # 切换界面时清除所有残留动画
        TWEEN.kill_all()
        self.current_screen = screen_class(self, **kwargs)

    def run(self, start_screen=None):
        """启动主循环。

        Args:
            start_screen: 可选的起始界面类，默认为 MenuScreen
        """
        pygame.init()
        self.screen = pygame.display.set_mode((self.WIN_W, self.WIN_H))
        pygame.display.set_caption("玩具大乱斗 TroopWar")
        _icon_path = Path(__file__).parent.parent.parent / "icon.png"
        if _icon_path.exists():
            pygame.display.set_icon(pygame.image.load(str(_icon_path)))
        self.clock = pygame.time.Clock()
        self.running = True

        # 预渲染所有图标缓存（一次性绘制，后续直接blit）
        from .render_cache import pre_render_all_icons
        pre_render_all_icons(use_persist_cache=True)

        # 延迟导入避免循环依赖
        if start_screen is not None:
            self.switch_to(start_screen)
        else:
            from .menu_screen import MenuScreen
            self.switch_to(MenuScreen)

        while self.running:
            dt = self.clock.tick(60) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.running = False
                    break
                if self.current_screen:
                    self.current_screen.handle_event(ev)
            if not self.running:
                break
            # 更新全局缓动动画
            TWEEN.update(dt)
            if self.current_screen:
                self.current_screen.update(dt)
                self.current_screen.draw(self.screen)
            pygame.display.flip()

        pygame.quit()