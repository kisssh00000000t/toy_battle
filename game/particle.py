"""
粒子碎屑特效系统。

核心类：
    Particle: 单个粒子（位置/速度/生命/颜色/重力）
    ParticleSystem: 粒子系统管理器（批量更新/绘制/回收）

使用方式：
    psys = ParticleSystem()
    psys.emit(x, y, count=12, color=(255, 200, 0))
    # 每帧更新
    psys.update()
    # 每帧绘制
    psys.draw(surface)
"""

import random
import math
from dataclasses import dataclass, field


@dataclass
class Particle:
    """单个粒子。

    Attributes:
        x, y: 位置（屏幕坐标）
        vx, vy: 速度（像素/帧）
        life: 剩余生命帧数
        max_life: 最大生命帧数（用于计算 alpha 衰减）
        color: RGB 颜色元组
        size: 粒子半径（像素）
        gravity: 重力加速度（像素/帧²，正值向下）
    """
    x: float
    y: float
    vx: float
    vy: float
    life: int
    max_life: int
    color: tuple[int, int, int]
    size: float = 3.0
    gravity: float = 0.15


class ParticleSystem:
    """粒子系统管理器。

    特性：
    - 批量发射粒子（随机速度/方向/颜色偏移）
    - 每帧更新位置、生命、alpha 衰减
    - 自动回收死亡粒子
    - 支持多种预设发射模式

    Attributes:
        particles: 当前活跃粒子列表
    """

    def __init__(self):
        self.particles: list[Particle] = []

    def emit(
        self,
        x: float,
        y: float,
        count: int = 12,
        color: tuple[int, int, int] = (255, 200, 0),
        speed: float = 3.0,
        life: int = 30,
        size: float = 3.0,
        gravity: float = 0.15,
        spread: float = 360.0,
        color_variance: int = 30,
    ) -> None:
        """在指定位置发射粒子。

        Args:
            x, y: 发射中心（屏幕坐标）
            count: 粒子数量
            color: 基础 RGB 颜色
            speed: 初始速度范围
            life: 粒子生命帧数
            size: 粒子半径
            gravity: 重力加速度
            spread: 发射角度范围（度），360=全方向
            color_variance: 颜色随机偏移幅度
        """
        for _ in range(count):
            angle = random.uniform(0, math.radians(spread))
            spd = random.uniform(speed * 0.3, speed)
            vx = spd * math.cos(angle)
            vy = spd * math.sin(angle)
            # 颜色偏移
            r = max(0, min(255, color[0] + random.randint(-color_variance, color_variance)))
            g = max(0, min(255, color[1] + random.randint(-color_variance, color_variance)))
            b = max(0, min(255, color[2] + random.randint(-color_variance, color_variance)))
            p = Particle(
                x=x + random.uniform(-2, 2),
                y=y + random.uniform(-2, 2),
                vx=vx,
                vy=vy,
                life=life + random.randint(-5, 5),
                max_life=life,
                color=(r, g, b),
                size=size + random.uniform(-1, 1),
                gravity=gravity,
            )
            self.particles.append(p)

    def emit_star_capture(
        self,
        x: float,
        y: float,
        color: tuple[int, int, int] = (255, 210, 0),
    ) -> None:
        """占领星星时的金色碎屑特效。

        Args:
            x, y: 星星屏幕坐标
            color: 碎屑颜色（默认金色）
        """
        self.emit(x, y, count=16, color=color, speed=4.0, life=30,
                  size=3.0, gravity=0.12, spread=360.0, color_variance=40)

    def emit_troop_place(
        self,
        x: float,
        y: float,
        color: tuple[int, int, int] = (200, 200, 200),
    ) -> None:
        """放置兵种时的碎屑特效。

        Args:
            x, y: 节点屏幕坐标
            color: 碎屑颜色
        """
        self.emit(x, y, count=8, color=color, speed=2.5, life=20,
                  size=2.0, gravity=0.2, spread=360.0, color_variance=20)

    def emit_victory(
        self,
        x: float,
        y: float,
        color: tuple[int, int, int] = (255, 215, 0),
    ) -> None:
        """胜利时的烟花特效。

        Args:
            x, y: 烟花中心坐标
            color: 烟花颜色
        """
        self.emit(x, y, count=30, color=color, speed=5.0, life=40,
                  size=4.0, gravity=0.08, spread=360.0, color_variance=50)

    def update(self) -> None:
        """更新所有粒子（位置、速度、生命），回收死亡粒子。"""
        alive = []
        for p in self.particles:
            p.life -= 1
            if p.life <= 0:
                continue
            p.vy += p.gravity
            p.x += p.vx
            p.y += p.vy
            # 空气阻力
            p.vx *= 0.97
            p.vy *= 0.97
            alive.append(p)
        self.particles = alive

    def draw(self, surface) -> None:
        """绘制所有活跃粒子。

        使用 alpha 衰减实现淡出效果。

        Args:
            surface: pygame.Surface 绘制目标
        """
        import pygame

        for p in self.particles:
            # alpha 衰减：生命越少越透明
            alpha = max(0, min(255, int(255 * p.life / p.max_life)))
            size = max(1, int(p.size * (p.life / p.max_life)))

            # 创建临时 Surface 实现半透明
            if size <= 1:
                # 单像素粒子直接绘制
                if alpha > 128:
                    surface.set_at((int(p.x), int(p.y)), p.color)
            else:
                # 多像素粒子使用临时 Surface
                ps = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                pygame.draw.circle(ps, (*p.color, alpha), (size, size), size)
                surface.blit(ps, (int(p.x) - size, int(p.y) - size))

    @property
    def count(self) -> int:
        """当前活跃粒子数。"""
        return len(self.particles)

    def clear(self) -> None:
        """清除所有粒子。"""
        self.particles.clear()