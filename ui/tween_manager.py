"""
全局 Tween 动画管理器。

提供属性插值动画，支持 int/float/pygame.Vector2 类型的缓动插值。
用法：
    from ui.tween_manager import TWEEN
    TWEEN.create_tween(obj, "x", 100, duration=0.3, ease_type=EASE_BACK_OUT)
    # 在游戏循环中调用 TWEEN.update(dt)
"""

import pygame

from .easing import ease_func


class Tween:
    """单个属性插值动画。"""

    def __init__(self, target, prop_name, start_val, end_val, duration, delay, ease_type, on_complete=None):
        self.target = target
        self.prop_name = prop_name
        self.start_val = start_val
        self.end_val = end_val
        self.duration = duration
        self.delay = delay
        self.ease_type = ease_type
        self.on_complete = on_complete
        self.elapsed = 0.0
        self.finished = False

    def update(self, dt):
        """每帧更新，推进动画进度。"""
        if self.finished:
            return
        self.elapsed += dt
        if self.elapsed < self.delay:
            return
        run_t = self.elapsed - self.delay
        t = min(run_t / self.duration, 1.0) if self.duration > 0 else 1.0
        t = max(0.0, min(1.0, t))  # 钳位确保 [0,1]
        eased_t = ease_func(self.ease_type, t)
        eased_t = max(0.0, min(1.0, eased_t))  # 二次保障：弹性缓动可能超范围

        start = self.start_val
        end = self.end_val
        if isinstance(start, pygame.Vector2):
            new_val = start.lerp(end, eased_t)
            setattr(self.target, self.prop_name, new_val)
        elif isinstance(start, (int, float)):
            new_val = start + (end - start) * eased_t
            # 保持原类型
            if isinstance(start, int):
                new_val = round(new_val)
            setattr(self.target, self.prop_name, new_val)
        else:
            setattr(self.target, self.prop_name, end)

        if t >= 1.0:
            self.finished = True
            if self.on_complete:
                self.on_complete()


class TweenManager:
    """全局 Tween 管理器（单例）。"""

    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.active_tweens = []
        return cls._instance

    def create_tween(self, target, prop_name, end_val, duration, delay=0.0,
                     ease_type=0, on_complete=None):
        """创建并启动一个属性动画，自动销毁同目标同属性的旧动画。

        Args:
            target: 目标对象
            prop_name: 属性名（字符串）
            end_val: 目标值
            duration: 动画时长（秒）
            delay: 延迟启动时间（秒）
            ease_type: 缓动类型ID（见 easing.py）
            on_complete: 动画完成回调（可选）
        Returns:
            Tween 实例
        """
        start_val = getattr(target, prop_name)
        self.kill_tween(target, prop_name)
        tw = Tween(target, prop_name, start_val, end_val, duration, delay, ease_type, on_complete)
        self.active_tweens.append(tw)
        return tw

    def kill_tween(self, target, prop_name):
        """停止目标对象指定属性的所有动画。"""
        self.active_tweens = [
            tw for tw in self.active_tweens
            if not (tw.target is target and tw.prop_name == prop_name)
        ]

    def kill_all(self):
        """停止所有动画。"""
        self.active_tweens.clear()

    def update(self, dt):
        """每帧更新所有活跃动画，移除已完成的。"""
        still_active = []
        for tw in self.active_tweens:
            tw.update(dt)
            if not tw.finished:
                still_active.append(tw)
        self.active_tweens = still_active


# 全局单例，方便导入
TWEEN = TweenManager()