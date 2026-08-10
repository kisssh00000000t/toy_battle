"""
Godot 风格缓动数学库。

提供 31 种缓动函数，覆盖线性、正弦、二次、三次、四次、五次、
指数、圆弧、回弹、弹性、弹跳等全部常用曲线。
"""

import math

# ─── 缓动类型常量 ────────────────────────────────────────────
EASE_LINEAR = 0
EASE_SINE_IN, EASE_SINE_OUT, EASE_SINE_IN_OUT = 1, 2, 3
EASE_QUAD_IN, EASE_QUAD_OUT, EASE_QUAD_IN_OUT = 4, 5, 6
EASE_CUBIC_IN, EASE_CUBIC_OUT, EASE_CUBIC_IN_OUT = 7, 8, 9
EASE_QUART_IN, EASE_QUART_OUT, EASE_QUART_IN_OUT = 10, 11, 12
EASE_QUINT_IN, EASE_QUINT_OUT, EASE_QUINT_IN_OUT = 13, 14, 15
EASE_EXPO_IN, EASE_EXPO_OUT, EASE_EXPO_IN_OUT = 16, 17, 18
EASE_CIRC_IN, EASE_CIRC_OUT, EASE_CIRC_IN_OUT = 19, 20, 21
EASE_BACK_IN, EASE_BACK_OUT, EASE_BACK_IN_OUT = 22, 23, 24
EASE_ELASTIC_IN, EASE_ELASTIC_OUT, EASE_ELASTIC_IN_OUT = 25, 26, 27
EASE_BOUNCE_IN, EASE_BOUNCE_OUT, EASE_BOUNCE_IN_OUT = 28, 29, 30


def ease_func(type_id: int, t: float) -> float:
    """缓动函数调度器。t ∈ [0,1]，返回映射后的进度值。"""
    if type_id == EASE_LINEAR:
        return t

    # ── Sine ──
    if type_id == EASE_SINE_IN:
        return 1 - math.cos(t * math.pi / 2)
    if type_id == EASE_SINE_OUT:
        return math.sin(t * math.pi / 2)
    if type_id == EASE_SINE_IN_OUT:
        return -(math.cos(math.pi * t) - 1) / 2

    # ── Quad ──
    if type_id == EASE_QUAD_IN:
        return t * t
    if type_id == EASE_QUAD_OUT:
        return 1 - (1 - t) * (1 - t)
    if type_id == EASE_QUAD_IN_OUT:
        return 2 * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 2) / 2

    # ── Cubic ──
    if type_id == EASE_CUBIC_IN:
        return t * t * t
    if type_id == EASE_CUBIC_OUT:
        return 1 - pow(1 - t, 3)
    if type_id == EASE_CUBIC_IN_OUT:
        return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2

    # ── Quart ──
    if type_id == EASE_QUART_IN:
        return t ** 4
    if type_id == EASE_QUART_OUT:
        return 1 - pow(1 - t, 4)
    if type_id == EASE_QUART_IN_OUT:
        return 8 * t ** 4 if t < 0.5 else 1 - pow(-2 * t + 2, 4) / 2

    # ── Quint ──
    if type_id == EASE_QUINT_IN:
        return t ** 5
    if type_id == EASE_QUINT_OUT:
        return 1 - pow(1 - t, 5)
    if type_id == EASE_QUINT_IN_OUT:
        return 16 * t ** 5 if t < 0.5 else 1 - pow(-2 * t + 2, 5) / 2

    # ── Expo ──
    if type_id == EASE_EXPO_IN:
        return 0 if t == 0 else math.pow(2, 10 * t - 10)
    if type_id == EASE_EXPO_OUT:
        return 1 if t == 1 else 1 - math.pow(2, -10 * t)
    if type_id == EASE_EXPO_IN_OUT:
        if t == 0 or t == 1:
            return t
        return math.pow(2, 20 * t - 10) / 2 if t < 0.5 else (2 - math.pow(2, -20 * t + 10)) / 2

    # ── Circ ──
    if type_id == EASE_CIRC_IN:
        return 1 - math.sqrt(1 - t * t)
    if type_id == EASE_CIRC_OUT:
        return math.sqrt(1 - pow(t - 1, 2))
    if type_id == EASE_CIRC_IN_OUT:
        if t < 0.5:
            return (1 - math.sqrt(1 - (2 * t) ** 2)) / 2
        return (math.sqrt(1 - pow(-2 * t + 2, 2)) + 1) / 2

    # ── Back (弹簧过冲) ──
    if type_id == EASE_BACK_IN:
        c1, c3 = 1.70158, 2.70158
        return c3 * t ** 3 - c1 * t * t
    if type_id == EASE_BACK_OUT:
        c1, c3 = 1.70158, 2.70158
        return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)
    if type_id == EASE_BACK_IN_OUT:
        c2 = 1.70158 * 1.525
        if t < 0.5:
            return (pow(2 * t, 2) * ((c2 + 1) * 2 * t - c2)) / 2
        return (pow(2 * t - 2, 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2

    # ── Elastic (强弹簧) ──
    if type_id == EASE_ELASTIC_IN:
        if t == 0 or t == 1:
            return t
        c4 = (2 * math.pi) / 3
        return -pow(2, 10 * t - 10) * math.sin((t * 10 - 10.75) * c4)
    if type_id == EASE_ELASTIC_OUT:
        if t == 0 or t == 1:
            return t
        c4 = (2 * math.pi) / 3
        return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * c4) + 1
    if type_id == EASE_ELASTIC_IN_OUT:
        if t == 0 or t == 1:
            return t
        if t < 0.5:
            return -(pow(2, 20 * t - 10) * math.sin((20 * t - 11.125) * (2 * math.pi) / 4.5)) / 2
        return pow(2, -20 * t + 10) * math.sin((20 * t - 11.125) * (2 * math.pi) / 4.5) / 2 + 1

    # ── Bounce (弹跳) ──
    if type_id == EASE_BOUNCE_IN:
        return 1 - ease_func(EASE_BOUNCE_OUT, 1 - t)
    if type_id == EASE_BOUNCE_OUT:
        n1, d1 = 7.5625, 2.75
        if t < 1 / d1:
            return n1 * t * t
        elif t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75
        elif t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375
        else:
            t -= 2.625 / d1
            return n1 * t * t + 0.984375
    if type_id == EASE_BOUNCE_IN_OUT:
        if t < 0.5:
            return (1 - ease_func(EASE_BOUNCE_OUT, 1 - 2 * t)) / 2
        return (1 + ease_func(EASE_BOUNCE_OUT, 2 * t - 1)) / 2

    # 安全兜底
    return t