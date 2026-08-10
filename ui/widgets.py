"""
玩具风格通用控件库。

玩具总动员扁平化卡通风格：圆角、阴影、高饱和马卡龙色、卡通字体。
纯Pygame几何图形渲染，不依赖外部图片素材。
支持 Godot 风格缓动动画（scale/rotation/alpha）。
"""

import math
import os
import platform
from pathlib import Path

import pygame

from .tween_manager import TWEEN
from .easing import EASE_BACK_OUT, EASE_LINEAR, EASE_QUART_OUT, EASE_ELASTIC_OUT
from .ui_const import FALLBACK_GRAY


# ─── 安全字体获取（本地优先 + 系统回退 + emoji + 字体缓存） ──────────
FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"
_font_cache = {}

def get_font(size, bold=False, style="chinese", allow_emoji=False):
    """获取一个能正常渲染的字体，优先本地字体文件，其次系统字体。

    Args:
        size: 字号
        style: 'chinese' 优先加载黑体（支持中文），
               'english' 优先加载 Comic Sans MS（卡通英文），
               'p2' 优先加载 P-2（标题/按钮装饰字体），
               'emoji' 优先加载彩色 emoji 字体
        allow_emoji: 如果为 True，优先尝试 emoji 字体（Segoe UI Emoji 等）
    """
    global _font_cache
    cache_key = (size, style)
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font = None

    # ── 0) emoji 优先路径 ──
    if allow_emoji or style == "emoji":
        emoji_names = [
            "Segoe UI Emoji", "Segoe UI Symbol",
            "Apple Color Emoji", "Noto Color Emoji",
        ]
        local_emoji = FONT_DIR / "seguiemj.ttf"
        try:
            if local_emoji.exists():
                f = pygame.font.Font(str(local_emoji), size)
                _font_cache[cache_key] = f
                return f
        except Exception:
            pass
        for name in emoji_names:
            try:
                f = pygame.font.SysFont(name, size)
                test_surf = f.render("\U0001F600", True, (0, 0, 0))
                if test_surf.get_width() > 5:
                    _font_cache[cache_key] = f
                    return f
            except Exception:
                continue

    # ── 1) P-2 装饰字体优先路径 ──
    if style == "p2":
        local_path = FONT_DIR / "P-2.ttf"
        try:
            if local_path.exists():
                f = pygame.font.Font(str(local_path), size)
                _font_cache[cache_key] = f
                return f
        except Exception:
            pass
        style = "chinese"

    # ── 2) 修复报错：确保所有 style 都有 sys_fonts 和 local_font_files ──
    if style == "chinese":
        sys_fonts = ["microsoftyahei", "msyh", "pingfang", "stheiti", "simhei"]
        local_font_files = ["msyh.ttc", "msyh.ttf", "simhei.ttf"]
    else:  # english
        sys_fonts = ["segoeui", "segoeuisymbol", "arial", "microsoftyahei"]
        local_font_files = ["arial.ttf", "comic.ttf", "simhei.ttf"]

    # ── 3) 终极解决符号变方块：Windows 下直接物理加载微软雅黑 ──
    if platform.system() == "Windows":
        msyh_path = os.path.join(
            os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msyh.ttc"
        )
        if os.path.exists(msyh_path):
            try:
                font = pygame.font.Font(msyh_path, size)
            except Exception:
                pass

    # ── 4) 其他系统或物理加载失败，尝试 Pygame SysFont ──
    if font is None:
        try:
            font = pygame.font.SysFont(sys_fonts, size)
        except Exception:
            pass

    # ── 5) SysFont 也失败，回退加载项目 assets/fonts/ ──
    if font is None or getattr(font, 'name', '') == 'pygame':
        for lf in local_font_files:
            lf_path = FONT_DIR / lf
            try:
                if lf_path.exists():
                    font = pygame.font.Font(str(lf_path), size)
                    break
            except Exception:
                pass

    # ── 6) 终极保底，防止崩溃 ──
    if font is None:
        font = pygame.font.Font(None, size)

    _font_cache[cache_key] = font
    return font

# ─── 玩具总动员扁平化主题配色 ─────────────────────────────────
TOY_COLORS = {
    "bg_cream":       (255, 248, 230),   # 主背景奶油白
    "primary_yellow": (255, 200, 50),    # 主按钮亮黄
    "secondary_cyan": (50, 200, 200),    # 辅助青蓝
    "accent_coral":   (255, 100, 100),   # 强调珊瑚红
    "soft_blue":      (120, 180, 255),   # 柔蓝
    "dark_text":      (40, 40, 50),      # 深色文字
    "light_text":     (255, 255, 255),   # 浅色文字
    "shadow":         (180, 170, 150),   # 阴影色
    "panel_bg":       (255, 253, 245),   # 面板背景
    "panel_stroke":   (220, 200, 170),   # 面板边框
    "success_green":  (80, 200, 120),    # 成功绿
    "danger_red":     (220, 60, 60),     # 危险红
    "soft_purple":    (180, 130, 255),   # 柔紫
    "warm_orange":    (255, 160, 60),    # 暖橙
}


# ─── 通用绘制工具 ───────────────────────────────────────────────

def draw_rounded_rect(surface, color, rect, radius=16, stroke_width=0, stroke_color=None):
    """绘制圆角矩形。"""
    rect = pygame.Rect(rect)
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if stroke_width > 0 and stroke_color:
        pygame.draw.rect(surface, stroke_color, rect, width=stroke_width, border_radius=radius)


def lighten_color(color, offset=40):
    """颜色变亮。"""
    return tuple(min(255, c + offset) for c in color)


def darken_color(color, offset=40):
    """颜色变暗。"""
    return tuple(max(0, c - offset) for c in color)


def get_contrast_border(base_color, dark_offset=60, bright_offset=80):
    """根据亮度自动计算对撞色边框：亮色→暗边框，暗色→亮边框。"""
    r, g, b = base_color
    brightness = r * 0.299 + g * 0.587 + b * 0.114
    if brightness > 130:
        return darken_color(base_color, dark_offset)
    else:
        return lighten_color(base_color, bright_offset)


def get_border_color(terrain_key):
    """获取地形边框颜色：优先使用 TERRAIN_DATA 中的 border_color，否则自动计算。"""
    from game.constants import TERRAIN_DATA
    td = TERRAIN_DATA.get(terrain_key, {})
    if "border_color" in td:
        return td["border_color"]
    return get_contrast_border(td.get("color", FALLBACK_GRAY))


def draw_star_shape(surface, cx, cy, size, fill_color, stroke_color=(0, 0, 0),
                    stroke_width=2, filled=True):
    """绘制纯几何五角星。

    Args:
        surface: Pygame Surface
        cx, cy: 星星中心坐标
        size: 外径（顶点到中心的距离）
        fill_color: 填充颜色
        stroke_color: 描边颜色
        stroke_width: 描边宽度
        filled: True=实心星，False=空心星（仅描边）
    """
    import math
    points = []
    for i in range(5):
        # 外顶点
        angle_outer = math.radians(-90 + i * 72)
        ox = cx + size * math.cos(angle_outer)
        oy = cy + size * math.sin(angle_outer)
        points.append((ox, oy))
        # 内顶点
        angle_inner = math.radians(-90 + i * 72 + 36)
        inner_r = size * 0.382  # 内径比 ≈ 0.382
        ix = cx + inner_r * math.cos(angle_inner)
        iy = cy + inner_r * math.sin(angle_inner)
        points.append((ix, iy))
    if filled:
        pygame.draw.polygon(surface, fill_color, points)
    if stroke_width > 0:
        pygame.draw.polygon(surface, stroke_color, points, stroke_width)


# ─── 兵种几何图标绘制（无emoji依赖） ──────────────────────────

def draw_troop_icon(surface, cx, cy, size, troop_key, owner_color, style_id: int = 1):
    """绘制兵种几何图标。

    Args:
        surface: Pygame Surface
        cx, cy: 图标中心坐标
        size: 图标外径
        troop_key: 兵种key (str "joker" or int 1~17)
        owner_color: 归属方颜色
        style_id: 图标样式编号，用于扩展兵种占位符文字选择
    """
    import math as _m
    r = size / 2
    white = (255, 255, 255)
    black = (0, 0, 0)
    sw = max(1, int(size / 10))  # 描边宽度

    if troop_key == "joker":
        # 橡皮鸭：椭圆身体+小圆头
        body_rect = pygame.Rect(cx - r * 0.8, cy - r * 0.3, r * 1.6, r * 1.0)
        pygame.draw.ellipse(surface, owner_color, body_rect)
        pygame.draw.ellipse(surface, black, body_rect, sw)
        # 头
        head_r = int(r * 0.35)
        hx = int(cx + r * 0.5)
        hy = int(cy - r * 0.3)
        pygame.draw.circle(surface, owner_color, (hx, hy), head_r)
        pygame.draw.circle(surface, black, (hx, hy), head_r, sw)
        # 嘴
        beak_pts = [(hx + head_r, hy), (hx + head_r + int(r * 0.3), hy - int(r * 0.1)),
                     (hx + head_r, hy + int(r * 0.15))]
        pygame.draw.polygon(surface, (255, 200, 50), beak_pts)
    elif troop_key == 1:
        # 小骷髅：圆形头骨+十字眼
        pygame.draw.circle(surface, white, (int(cx), int(cy)), int(r))
        pygame.draw.circle(surface, black, (int(cx), int(cy)), int(r), sw)
        # 眼眶十字
        ew = max(2, int(r * 0.3))
        pygame.draw.line(surface, black, (int(cx - ew), int(cy - ew // 2)),
                         (int(cx - ew // 3), int(cy - ew // 2)), max(2, sw))
        pygame.draw.line(surface, black, (int(cx + ew // 3), int(cy - ew // 2)),
                         (int(cx + ew), int(cy - ew // 2)), max(2, sw))
        # 嘴
        pygame.draw.line(surface, black, (int(cx - ew // 2), int(cy + ew // 2)),
                         (int(cx + ew // 2), int(cy + ew // 2)), max(1, sw))
    elif troop_key == 2:
        # 玩具队长：船锚
        pygame.draw.line(surface, white, (int(cx), int(cy - r * 0.8)),
                         (int(cx), int(cy + r * 0.5)), max(2, sw + 1))
        # 横杠
        pygame.draw.line(surface, white, (int(cx - r * 0.3), int(cy - r * 0.5)),
                         (int(cx + r * 0.3), int(cy - r * 0.5)), max(2, sw))
        # 底部弧
        arc_rect = pygame.Rect(int(cx - r * 0.6), int(cy - r * 0.1),
                               int(r * 1.2), int(r * 0.9))
        pygame.draw.arc(surface, white, arc_rect, _m.radians(0), _m.radians(180), max(2, sw))
    elif troop_key == 3:
        # 重装骑士：盾牌
        sh_w = int(r * 1.2)
        sh_h = int(r * 1.6)
        sh_rect = pygame.Rect(int(cx - sh_w // 2), int(cy - sh_h // 2), sh_w, sh_h)
        pygame.draw.rect(surface, white, sh_rect, border_radius=4)
        pygame.draw.rect(surface, black, sh_rect, sw, border_radius=4)
        # 盾面十字
        pygame.draw.line(surface, owner_color, (int(cx), int(cy - sh_h // 2 + 4)),
                         (int(cx), int(cy + sh_h // 2 - 4)), max(2, sw))
        pygame.draw.line(surface, owner_color, (int(cx - sh_w // 2 + 4), int(cy)),
                         (int(cx + sh_w // 2 - 4), int(cy)), max(2, sw))
    elif troop_key == 4:
        # 飞钩船长：钩子
        pygame.draw.line(surface, white, (int(cx), int(cy - r * 0.8)),
                         (int(cx), int(cy + r * 0.1)), max(2, sw + 1))
        # 钩弧
        hook_rect = pygame.Rect(int(cx - r * 0.5), int(cy - r * 0.1),
                                int(r * 1.0), int(r * 0.8))
        pygame.draw.arc(surface, white, hook_rect, _m.radians(270), _m.radians(90), max(2, sw))
    elif troop_key == 5:
        # XB-42：飞机三角
        pts = [(int(cx), int(cy - r * 0.8)),
               (int(cx - r * 0.7), int(cy + r * 0.5)),
               (int(cx + r * 0.7), int(cy + r * 0.5))]
        pygame.draw.polygon(surface, white, pts)
        pygame.draw.polygon(surface, black, pts, sw)
        # 机身线
        pygame.draw.line(surface, owner_color, (int(cx), int(cy - r * 0.5)),
                         (int(cx), int(cy + r * 0.3)), max(1, sw))
    elif troop_key == 6:
        # 独角兽星耀：五角星（复用draw_star_shape）
        draw_star_shape(surface, int(cx), int(cy), int(r * 0.8), white, black, sw, filled=True)
    elif troop_key == 7:
        # 暴龙萝西：恐龙简化椭圆+小头
        body_rect = pygame.Rect(int(cx - r * 0.7), int(cy - r * 0.2),
                                int(r * 1.4), int(r * 0.8))
        pygame.draw.ellipse(surface, white, body_rect)
        pygame.draw.ellipse(surface, black, body_rect, sw)
        # 小头
        head_r = int(r * 0.3)
        hx = int(cx + r * 0.6)
        hy = int(cy - r * 0.3)
        pygame.draw.circle(surface, white, (hx, hy), head_r)
        pygame.draw.circle(surface, black, (hx, hy), head_r, sw)
        # 眼
        pygame.draw.circle(surface, black, (hx + int(r * 0.1), hy - int(r * 0.05)),
                           max(1, int(r * 0.08)))
    else:
        # 扩展兵种占位符：根据样式显示不同文字
        from game.constants import TROOP_DATA
        data = TROOP_DATA.get(troop_key, {})
        if style_id == 1 and data.get("name"):
            # 样式1：中文首字
            label = data["name"][0]
        elif style_id == 2 and data.get("symbol"):
            # 样式2：英文缩写两字母
            label = data["symbol"]
        else:
            # 兜底：问号
            label = "?"
        # 绘制底圆 + 文字
        pygame.draw.circle(surface, owner_color, (int(cx), int(cy)), int(r))
        pygame.draw.circle(surface, black, (int(cx), int(cy)), int(r), sw)
        font_size = max(12, int(r * 1.1))
        if len(label) > 1:
            font_size = max(10, int(r * 0.7))
        font = get_font(font_size, bold=True, style="chinese")
        txt_surf = font.render(label, True, white)
        txt_rect = txt_surf.get_rect(center=(int(cx), int(cy)))
        surface.blit(txt_surf, txt_rect)


# ─── 地形几何图标绘制（无emoji依赖） ──────────────────────────

def draw_terrain_icon(surface, cx, cy, size, terrain_key, fill_color):
    """绘制地形几何图标。

    Args:
        surface: Pygame Surface
        cx, cy: 图标中心坐标
        size: 图标外径
        terrain_key: 地形key
        fill_color: 地形填充颜色
    """
    import math as _m
    r = size / 2
    white = (255, 255, 255)
    black = (0, 0, 0)
    sw = max(1, int(size / 12))

    if terrain_key == "castle_field":
        # 城堡：三个方块塔楼
        tw = int(r * 0.5)
        th = int(r * 0.7)
        for dx in [-r * 0.5, 0, r * 0.5]:
            rect = pygame.Rect(int(cx + dx - tw // 2), int(cy - th // 2), tw, th)
            pygame.draw.rect(surface, white, rect, border_radius=2)
            pygame.draw.rect(surface, black, rect, sw, border_radius=2)
    elif terrain_key == "tropical_pool":
        # 泳池：波浪线
        for i in range(3):
            oy = int(cy - r * 0.4 + i * r * 0.4)
            pts = []
            for x_off in range(int(-r * 0.7), int(r * 0.7), 3):
                y_wave = oy + int(r * 0.12 * _m.sin(x_off * 0.15 + i))
                pts.append((int(cx + x_off), y_wave))
            if len(pts) > 1:
                pygame.draw.lines(surface, white, False, pts, max(2, sw))
    elif terrain_key == "city_of_clouds":
        # 云之城：三个重叠圆
        for dx in [-r * 0.35, 0, r * 0.35]:
            cr = int(r * 0.35)
            pygame.draw.circle(surface, white, (int(cx + dx), int(cy)), cr)
            pygame.draw.circle(surface, black, (int(cx + dx), int(cy)), cr, sw)
    elif terrain_key == "volcanic_jungle":
        # 火山：三角
        pts = [(int(cx), int(cy - r * 0.8)),
               (int(cx - r * 0.7), int(cy + r * 0.6)),
               (int(cx + r * 0.7), int(cy + r * 0.6))]
        pygame.draw.polygon(surface, white, pts)
        pygame.draw.polygon(surface, black, pts, sw)
    elif terrain_key == "cursed_cemetery":
        # 墓碑：圆顶矩形
        sw_rect = int(r * 0.5)
        sh = int(r * 1.2)
        rect = pygame.Rect(int(cx - sw_rect // 2), int(cy - sh // 2), sw_rect, sh)
        pygame.draw.rect(surface, white, rect, border_radius=int(r * 0.25))
        pygame.draw.rect(surface, black, rect, sw, border_radius=int(r * 0.25))
    elif terrain_key == "caribbean_sea":
        # 加勒比海：三层波浪横线
        for i in range(3):
            oy = int(cy - r * 0.4 + i * r * 0.4)
            pygame.draw.line(surface, white, (int(cx - r * 0.6), oy),
                             (int(cx + r * 0.6), oy), max(2, sw))
    elif terrain_key == "station_metalx":
        # 金属X站：齿轮十字
        pygame.draw.line(surface, white, (int(cx - r * 0.6), int(cy)),
                         (int(cx + r * 0.6), int(cy)), max(2, sw + 1))
        pygame.draw.line(surface, white, (int(cx), int(cy - r * 0.6)),
                         (int(cx), int(cy + r * 0.6)), max(2, sw + 1))
        # 对角线
        d = r * 0.42
        pygame.draw.line(surface, white, (int(cx - d), int(cy - d)),
                         (int(cx + d), int(cy + d)), max(1, sw))
        pygame.draw.line(surface, white, (int(cx + d), int(cy - d)),
                         (int(cx - d), int(cy + d)), max(1, sw))
    elif terrain_key == "battlefield":
        # 古战场：交叉刀剑
        pygame.draw.line(surface, white, (int(cx - r * 0.6), int(cy - r * 0.6)),
                         (int(cx + r * 0.6), int(cy + r * 0.6)), max(2, sw))
        pygame.draw.line(surface, white, (int(cx + r * 0.6), int(cy - r * 0.6)),
                         (int(cx - r * 0.6), int(cy + r * 0.6)), max(2, sw))
    elif terrain_key == "normal":
        # 普通据点：小圆点
        pygame.draw.circle(surface, white, (int(cx), int(cy)), max(2, int(r * 0.25)))
    else:
        # 未知地形：小菱形
        pts = [(int(cx), int(cy - r * 0.5)), (int(cx + r * 0.5), int(cy)),
               (int(cx), int(cy + r * 0.5)), (int(cx - r * 0.5), int(cy))]
        pygame.draw.polygon(surface, white, pts)


# ─── 玩具圆角按钮（带缓动动画） ────────────────────────────────

class ToyButton:
    """玩具风格圆角按钮，带阴影、悬停/按压效果和缓动动画。

    动效属性：
        scale: pygame.Vector2 缩放因子 (1,1 为原始大小)
        rotation: float 旋转弧度
        alpha: int 透明度 0~255
    """

    def __init__(self, text, rect, callback, color=None, icon_type=None):
        color = color or TOY_COLORS["primary_yellow"]
        self.text = text
        self.rect = pygame.Rect(rect)
        self.callback = callback
        self.base_color = color
        self.hover_color = lighten_color(color, 30)
        self.press_color = darken_color(color, 30)
        self.hover = False
        self.pressed = False
        self.enabled = True
        # 按钮文字含中英文混合，统一用P-2装饰字体
        self.font = get_font(22, bold=True, style="p2")
        # 纯绘制图标类型：play/edit/map/chart/draw/end/back/save/load/refresh/new
        self.icon_type = icon_type

        # ── 动效属性 ──
        self.scale = pygame.Vector2(1.0, 1.0)
        self.rotation = 0.0   # 弧度
        self.alpha = 255

        # 悬停动画参数
        self._hover_scale = 1.10
        self._hover_rot_deg = 3.0
        self._tween_dur = 0.12

        # ── 按压弹簧反馈 ──
        self.press_offset = 0      # 按下时向下偏移（像素）
        self.shadow_height = 3     # 阴影垂直偏移（按下时缩小）

    def _get_adjusted_rot(self):
        """根据按钮长宽比调整旋转幅度，防止长条按钮过度扭曲。"""
        w, h = self.rect.size
        ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 1.0
        base = self._hover_rot_deg
        if ratio > 1.8:
            return base * 0.4
        elif ratio > 1.3:
            return base * 0.7
        return base

    def handle_event(self, event):
        if not self.enabled:
            return
        if event.type == pygame.MOUSEMOTION:
            old_hover = self.hover
            self.hover = self.rect.collidepoint(event.pos)
            if self.hover and not old_hover:
                # 鼠标进入：缩放 + 轻微旋转（Back Out 弹簧）
                TWEEN.create_tween(
                    self, "scale",
                    pygame.Vector2(self._hover_scale, self._hover_scale),
                    self._tween_dur, 0, EASE_BACK_OUT)
                TWEEN.create_tween(
                    self, "rotation",
                    math.radians(self._get_adjusted_rot()),
                    self._tween_dur, 0, EASE_BACK_OUT)
            elif not self.hover and old_hover:
                # 鼠标离开：平滑恢复
                TWEEN.create_tween(
                    self, "scale", pygame.Vector2(1, 1),
                    self._tween_dur * 0.8, 0, EASE_LINEAR)
                TWEEN.create_tween(
                    self, "rotation", 0.0,
                    self._tween_dur * 0.8, 0, EASE_LINEAR)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.hover:
                self.pressed = True
                # 按下：阴影缩小 + 按钮下沉
                TWEEN.create_tween(
                    self, "press_offset", 3,
                    0.06, 0, EASE_LINEAR)
                TWEEN.create_tween(
                    self, "shadow_height", 1,
                    0.06, 0, EASE_LINEAR)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.pressed and self.hover:
                self.callback()
            self.pressed = False
            # 释放：弹簧回弹
            TWEEN.create_tween(
                self, "press_offset", 0,
                0.25, 0, EASE_ELASTIC_OUT)
            TWEEN.create_tween(
                self, "shadow_height", 3,
                0.25, 0, EASE_ELASTIC_OUT)

    def draw(self, surface):
        w, h = self.rect.size
        # 临时画布，略大于控件以防旋转裁剪
        pad = 24
        tmp_w, tmp_h = w + pad * 2, h + pad * 2
        tmp_surf = pygame.Surface((tmp_w, tmp_h), pygame.SRCALPHA)

        # 阴影（高度随按压变化）
        sh = int(self.shadow_height)
        draw_rounded_rect(tmp_surf, TOY_COLORS["shadow"],
                          pygame.Rect(pad + 3, pad + sh, w, h), radius=12)
        # 按钮主体（按压偏移）
        po = int(self.press_offset)
        if not self.enabled:
            draw_color = (180, 180, 180)
        elif self.pressed:
            draw_color = self.press_color
        elif self.hover:
            draw_color = self.hover_color
        else:
            draw_color = self.base_color
        draw_rounded_rect(tmp_surf, draw_color,
                          pygame.Rect(pad, pad + po, w, h), radius=12,
                          stroke_width=2, stroke_color=TOY_COLORS["dark_text"])
        # 文字
        text_color = TOY_COLORS["dark_text"] if self.enabled else (140, 140, 140)
        text_surf = self.font.render(self.text, True, text_color)
        # 计算图标偏移
        icon_w = 0
        icon_surf = None
        if self.icon_type:
            icon_surf = self._draw_icon(text_color)
            if icon_surf:
                icon_w = icon_surf.get_width() + 6
        # 文字居中（考虑图标宽度偏移 + 按压偏移）
        total_w = icon_w + text_surf.get_width()
        text_x = pad + (w - total_w) // 2
        text_y = pad + h // 2 + po
        if icon_surf:
            tmp_surf.blit(icon_surf, (text_x, text_y - icon_surf.get_height() // 2))
        tmp_surf.blit(text_surf, (text_x + icon_w, text_y - text_surf.get_height() // 2))

        # 透明度
        tmp_surf.set_alpha(int(self.alpha))

        # 缩放
        scaled = pygame.transform.scale(
            tmp_surf,
            (int(tmp_w * self.scale.x), int(tmp_h * self.scale.y)))
        # 旋转
        rotated = pygame.transform.rotate(scaled, math.degrees(self.rotation))
        # 保持中心不变
        draw_pos = pygame.Vector2(self.rect.center) - pygame.Vector2(rotated.get_size()) / 2
        surface.blit(rotated, draw_pos)

    # ── 纯绘制图标（无外部图片，纯几何图形） ──

    _ICON_SIZE = 18  # 图标基准尺寸

    def _draw_icon(self, color):
        """根据 icon_type 绘制纯几何图标 Surface。

        支持类型: play, edit, map, chart, draw, end, back, save, load, refresh, new, eval
        """
        s = self._ICON_SIZE
        surf = pygame.Surface((s + 4, s + 4), pygame.SRCALPHA)
        cx, cy = s // 2 + 2, s // 2 + 2
        itype = self.icon_type

        if itype == "play":
            # 三角形播放图标 \u25B6
            pts = [(cx - s // 3, cy - s // 2 + 1),
                   (cx - s // 3, cy + s // 2 - 1),
                   (cx + s // 2, cy)]
            pygame.draw.polygon(surf, color, pts)

        elif itype == "edit":
            # 铅笔图标 \u270E
            # 笔身
            pygame.draw.rect(surf, color, (cx - s // 3, cy - s // 3, s * 2 // 3, s // 3))
            # 笔尖
            pts = [(cx - s // 3, cy),
                   (cx + s // 3, cy),
                   (cx, cy + s // 2)]
            pygame.draw.polygon(surf, color, pts)

        elif itype == "map":
            # 地图图标：折叠矩形
            pygame.draw.rect(surf, color, (cx - s // 2, cy - s // 3, s, s * 2 // 3), 2)
            pygame.draw.line(surf, color, (cx, cy - s // 3), (cx, cy + s // 3), 2)

        elif itype == "chart":
            # 柱状图图标
            bw = s // 5
            pygame.draw.rect(surf, color, (cx - s // 2, cy, bw, s // 3))
            pygame.draw.rect(surf, color, (cx - s // 2 + bw + 2, cy - s // 6, bw, s // 3 + s // 6))
            pygame.draw.rect(surf, color, (cx + 2, cy - s // 3, bw, s // 3 * 2))

        elif itype == "draw":
            # 抽卡图标：叠放卡片
            pygame.draw.rect(surf, color, (cx - s // 3 + 2, cy - s // 3 + 2, s * 2 // 3, s * 2 // 3), 2)
            pygame.draw.rect(surf, color, (cx - s // 3, cy - s // 3, s * 2 // 3, s * 2 // 3), 2)

        elif itype == "end":
            # 结束图标：方块 \u25A0
            pygame.draw.rect(surf, color, (cx - s // 3, cy - s // 3, s * 2 // 3, s * 2 // 3))

        elif itype == "back":
            # 返回箭头 ←
            pygame.draw.line(surf, color, (cx + s // 3, cy), (cx - s // 3, cy), 2)
            pygame.draw.line(surf, color, (cx - s // 3, cy), (cx - s // 6, cy - s // 4), 2)
            pygame.draw.line(surf, color, (cx - s // 3, cy), (cx - s // 6, cy + s // 4), 2)

        elif itype == "save":
            # 保存图标：软盘
            pygame.draw.rect(surf, color, (cx - s // 3, cy - s // 3, s * 2 // 3, s * 2 // 3), 2)
            pygame.draw.rect(surf, color, (cx - s // 6, cy - s // 3, s // 3, s // 4))

        elif itype == "load":
            # 加载图标：向下箭头 + 横线
            pygame.draw.line(surf, color, (cx, cy - s // 3), (cx, cy + s // 4), 2)
            pygame.draw.line(surf, color, (cx, cy + s // 4), (cx - s // 5, cy), 2)
            pygame.draw.line(surf, color, (cx, cy + s // 4), (cx + s // 5, cy), 2)
            pygame.draw.line(surf, color, (cx - s // 3, cy + s // 3), (cx + s // 3, cy + s // 3), 2)

        elif itype == "refresh":
            # 刷新图标：循环箭头
            pygame.draw.arc(surf, color, (cx - s // 3, cy - s // 3, s * 2 // 3, s * 2 // 3),
                            0.5, 4.5, 2)
            pygame.draw.polygon(surf, color, [
                (cx + s // 4, cy - s // 6),
                (cx + s // 3, cy - s // 3),
                (cx + s // 8, cy - s // 3)])

        elif itype == "new":
            # 新建图标：+ 号
            pygame.draw.line(surf, color, (cx - s // 3, cy), (cx + s // 3, cy), 2)
            pygame.draw.line(surf, color, (cx, cy - s // 3), (cx, cy + s // 3), 2)

        elif itype == "eval":
            # 评估图标：对勾 \u2713
            pygame.draw.line(surf, color, (cx - s // 3, cy), (cx - s // 8, cy + s // 4), 2)
            pygame.draw.line(surf, color, (cx - s // 8, cy + s // 4), (cx + s // 3, cy - s // 4), 2)

        elif itype == "star":
            # 星星图标：五角星 \u2605
            import math as _m
            pts = []
            for i in range(5):
                a_out = _m.radians(-90 + i * 72)
                a_in = _m.radians(-90 + i * 72 + 36)
                pts.append((cx + s // 2 * _m.cos(a_out), cy + s // 2 * _m.sin(a_out)))
                pts.append((cx + s // 5 * _m.cos(a_in), cy + s // 5 * _m.sin(a_in)))
            pygame.draw.polygon(surf, color, pts)

        elif itype == "gear":
            # 齿轮图标 \u2699（直接使用Unicode字符）
            icon_font = pygame.font.SysFont("segoeuisymbol,arial,sans", s)
            char_surf = icon_font.render("\u2699", True, color)
            surf.blit(char_surf, (cx - char_surf.get_width() // 2, cy - char_surf.get_height() // 2))

        elif itype == "wire":
            # 连线图标：折线 /|
            pygame.draw.line(surf, color, (cx - s // 3, cy + s // 4), (cx, cy - s // 4), 2)
            pygame.draw.line(surf, color, (cx, cy - s // 4), (cx + s // 3, cy + s // 4), 2)
            pygame.draw.circle(surf, color, (cx - s // 3, cy + s // 4), 2)
            pygame.draw.circle(surf, color, (cx + s // 3, cy + s // 4), 2)

        else:
            return None

        return surf


# ─── 文本标签 ────────────────────────────────────────────────────

class ToyLabel:
    """玩具风格文本标签。"""

    def __init__(self, text, pos, font_size=32, color=None):
        color = color or TOY_COLORS["dark_text"]
        self.text = text
        self.x, self.y = pos
        self.font_size = font_size
        self.color = color
        self._font = None
        # 动效属性
        self.alpha = 255

    @property
    def font(self):
        if self._font is None:
            # 标签含中英文混合，统一用中文字体确保可见
            self._font = get_font(self.font_size, bold=True, style="chinese")
        return self._font

    def draw(self, surface):
        surf = self.font.render(self.text, True, self.color)
        tmp = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        tmp.blit(surf, (0, 0))
        tmp.set_alpha(int(self.alpha))
        surface.blit(tmp, (self.x, self.y))


# ─── 数值动画标签 ────────────────────────────────────────────────

class NumAnimateLabel(ToyLabel):
    """数值标签，支持数字滚动 + 弹跳反馈。

    用 set_value() 更新数值，自动播放滚动和弹跳动画。
    """

    def __init__(self, text, pos, font_size=32, color=None):
        super().__init__(text, pos, font_size, color)
        self._real_val = 0
        self.display_val = 0.0
        self.bounce_scale = 1.25
        self.anim_dur = 0.9
        self.scale = pygame.Vector2(1, 1)

    def set_value(self, new_val: int):
        """设置新数值，触发滚动+弹跳动画。"""
        if new_val == self._real_val:
            return
        self._real_val = new_val
        # 数字平滑滚动（Quart Out 平滑停止）
        TWEEN.create_tween(self, "display_val", float(new_val),
                           self.anim_dur, 0, EASE_QUART_OUT)
        # 延迟弹跳放大（Elastic Out）
        bounce_delay = self.anim_dur * 0.75
        TWEEN.create_tween(self, "scale",
                           pygame.Vector2(self.bounce_scale, self.bounce_scale),
                           0.15, bounce_delay, EASE_ELASTIC_OUT)
        TWEEN.create_tween(self, "scale", pygame.Vector2(1, 1),
                           0.15, bounce_delay + 0.15, EASE_LINEAR)

    def draw(self, surface):
        # 用 display_val 作为显示文本
        self.text = str(round(self.display_val))
        w, h = self.font.size(self.text)
        pad = 10
        tmp = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        surf = self.font.render(self.text, True, self.color)
        tmp.blit(surf, (pad, pad))
        # 缩放
        scaled = pygame.transform.scale(
            tmp,
            (int((w + pad * 2) * self.scale.x),
             int((h + pad * 2) * self.scale.y)))
        surface.blit(scaled, (self.x, self.y))


# ─── 圆角面板容器 ───────────────────────────────────────────────

class ToyPanel:
    """圆角面板容器，用于分组和背景。"""

    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        # 动效属性
        self.alpha = 255

    def draw(self, surface):
        tmp = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        draw_rounded_rect(tmp, TOY_COLORS["panel_bg"], pygame.Rect(0, 0, *self.rect.size),
                          radius=14, stroke_width=3, stroke_color=TOY_COLORS["panel_stroke"])
        tmp.set_alpha(int(self.alpha))
        surface.blit(tmp, self.rect.topleft)


# ─── 开关Toggle控件 ──────────────────────────────────────────────

class ToyToggle:
    """开关控件，支持布尔状态切换。"""

    def __init__(self, label, pos, callback, default=False):
        self.label = label
        self.x, self.y = pos
        self.callback = callback
        self.state = default
        self.width, self.height = 60, 30
        self.font = get_font(18, style="english")
        self.click_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        # 动效属性
        self.alpha = 255

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.click_rect.collidepoint(event.pos):
                self.state = not self.state
                self.callback(self.state)

    def draw(self, surface):
        tmp = pygame.Surface((self.width + 100, self.height + 10), pygame.SRCALPHA)
        bg_color = TOY_COLORS["secondary_cyan"] if self.state else FALLBACK_GRAY
        local_rect = pygame.Rect(0, 0, self.width, self.height)
        draw_rounded_rect(tmp, bg_color, local_rect, radius=15)
        circle_x = 35 if self.state else 5
        pygame.draw.circle(tmp, (255, 255, 255), (circle_x + 12, 15), 12)
        text = self.font.render(self.label, True, TOY_COLORS["dark_text"])
        tmp.blit(text, (self.width + 10, 4))
        tmp.set_alpha(int(self.alpha))
        surface.blit(tmp, (self.x, self.y))


# ─── 手牌卡片控件 ───────────────────────────────────────────────

class ToyCard:
    """玩具风格手牌卡片。"""

    def __init__(self, troop, rect, selected=False, player_color_name=None):
        self.troop = troop
        self.rect = pygame.Rect(rect)
        self.selected = selected
        self.hover = False
        self.player_color_name = player_color_name  # "red" / "blue"
        self.font_info = get_font(14, style="english")

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)

    def _macaron_border_color(self):
        """根据阵营返回马卡龙边框色。"""
        from .ui_const import TOY_RED_BORDER, TOY_BLUE_BORDER
        if self.player_color_name == "red":
            return TOY_RED_BORDER
        if self.player_color_name == "blue":
            return TOY_BLUE_BORDER
        return TOY_COLORS["dark_text"]

    def draw(self, surface, player_color_rgb):
        # 选中高亮
        if self.selected:
            glow = self.rect.inflate(8, 8)
            draw_rounded_rect(surface, (255, 220, 40), glow, radius=10)

        # 卡片主体
        card_color = player_color_rgb
        if self.selected:
            card_color = lighten_color(card_color, 60)
        elif self.hover:
            card_color = lighten_color(card_color, 30)
        draw_rounded_rect(surface, card_color, self.rect, radius=12)

        # 阵营色边框（马卡龙色调）
        border_col = self._macaron_border_color()
        pygame.draw.rect(surface, border_col, self.rect, width=2, border_radius=12)

        # ── 底座（增强图标视觉深度） ──
        base_radius = self.rect.height // 3
        base_center = (self.rect.centerx, self.rect.centery + 2)
        # 底座圆（马卡龙色）
        base_col = self._macaron_border_color()
        pygame.draw.circle(surface, base_col, base_center, base_radius)
        # 底座高光边缘
        highlight_color = lighten_color(base_col, 40)
        pygame.draw.circle(surface, highlight_color, base_center, base_radius, 2)

        # 兵种图标（缓存blit替代文字渲染）
        from .render_cache import get_cached_troop
        from game.constants import HAND_TROOP_ICON_SIZE
        icon_size = HAND_TROOP_ICON_SIZE
        tro_surf = get_cached_troop(self.troop.troop_key, self.troop.owner,
                                     target_size=icon_size)
        surface.blit(tro_surf, (self.rect.centerx - tro_surf.get_width() // 2,
                                self.rect.centery - tro_surf.get_height() // 2 - 12))
        # 战力
        val = str(self.troop.number) if self.troop.number else "J"
        val_surf = self.font_info.render(val, True, (255, 255, 255))
        surface.blit(val_surf, (self.rect.x + 4, self.rect.bottom - 18))


# ─── 玩具风标题组件（漂浮动效 + 星星装饰 + 悬浮交互） ──────────────

class ToyTitle:
    """玩具风卡通标题，带漂浮循环动效、四角星星装饰、鼠标悬浮回弹。

    纯 Pygame 几何图形渲染，不依赖外部图片。
    复用全局 TWEEN 缓动系统。
    """

    def __init__(self, text, center_x, center_y, font_size=72,
                 base_color=None, decor_count=4):
        base_color = base_color or TOY_COLORS["accent_coral"]
        self.text = text
        self.cx = center_x
        self.cy = center_y
        self.font_size = font_size
        self.base_color = base_color
        self.hover_color = lighten_color(base_color, 50)
        self.decor_count = decor_count

        # 动效属性
        self.scale = pygame.Vector2(1.0, 1.0)
        self.rotation = 0.0
        self.float_offset = 0.0
        self.hover = False
        self._base_float_range = 8
        self._hover_float_range = 16
        self._float_dir = 1  # 1=上, -1=下
        self._float_timer = 0.0
        self._float_period = 1.8  # 半周期秒

        # 装饰星星参数
        self.decor_list = []
        self._init_decor_pos()

    def _init_decor_pos(self):
        """生成标题四周装饰星星坐标。"""
        offsets = [(-130, -45), (110, -38), (-115, 50), (125, 42)]
        for i in range(min(self.decor_count, len(offsets))):
            ox, oy = offsets[i]
            self.decor_list.append({
                "dx": ox, "dy": oy,
                "phase": i * (math.pi / 2),
                "size": 12 + (i % 3) * 6,
            })

    @staticmethod
    def draw_star(surf, x, y, size, color):
        """使用缓存blit绘制五角星（装饰用，映射到缓存状态）。"""
        from .render_cache import get_cached_star
        # 装饰星星映射：暖色→red(金色), 冷色→gray(灰色)
        # 简单启发式：R通道大于B通道视为暖色
        if isinstance(color, (tuple, list)) and len(color) >= 3 and color[0] > color[2]:
            state = "red"
        else:
            state = "gray"
        star_surf = get_cached_star(state, size)
        surf.blit(star_surf, (x - star_surf.get_width() // 2,
                               y - star_surf.get_height() // 2))

    def update(self, dt):
        """更新漂浮循环动画。"""
        self._float_timer += dt
        if self._float_timer >= self._float_period:
            self._float_timer -= self._float_period
            self._float_dir *= -1
        # 正弦缓动
        t = self._float_timer / self._float_period
        ease_t = 0.5 - 0.5 * math.cos(t * math.pi)
        amp = self._hover_float_range if self.hover else self._base_float_range
        target = amp * self._float_dir * ease_t
        self.float_offset = target

    def handle_event(self, event):
        """鼠标悬浮检测。"""
        if event.type == pygame.MOUSEMOTION:
            font = get_font(self.font_size, bold=True, style="p2")
            text_surf = font.render(self.text, True, self.base_color)
            text_rect = text_surf.get_rect(center=(self.cx, self.cy + self.float_offset))
            # 扩大碰撞区域
            hit_rect = text_rect.inflate(40, 20)
            old_hover = self.hover
            self.hover = hit_rect.collidepoint(event.pos)
            if self.hover and not old_hover:
                TWEEN.create_tween(self, "scale",
                                   pygame.Vector2(1.12, 1.12), 0.15, 0, EASE_BACK_OUT)
                TWEEN.create_tween(self, "rotation",
                                   math.radians(2.2), 0.15, 0, EASE_BACK_OUT)
            elif not self.hover and old_hover:
                TWEEN.create_tween(self, "scale",
                                   pygame.Vector2(1, 1), 0.12, 0, EASE_LINEAR)
                TWEEN.create_tween(self, "rotation",
                                   0.0, 0.12, 0, EASE_LINEAR)

    def draw(self, surface):
        """绘制标题 + 装饰星星 + 描边。"""
        float_y = self.cy + self.float_offset
        font = get_font(self.font_size, bold=True, style="p2")
        color = self.hover_color if self.hover else self.base_color
        text_surf = font.render(self.text, True, color)
        tw, th = text_surf.get_size()

        # 临时画布
        pad = 80
        canvas_w, canvas_h = tw + pad * 2, th + pad * 2
        tmp = pygame.Surface((canvas_w, canvas_h), pygame.SRCALPHA)

        # 装饰星星
        for deco in self.decor_list:
            dx = deco["dx"]
            dy = deco["dy"] + math.sin(self.float_offset * 0.5 + deco["phase"]) * 4
            star_x = canvas_w / 2 + dx
            star_y = canvas_h / 2 + dy
            star_color = TOY_COLORS["primary_yellow"] if self.hover else TOY_COLORS["secondary_cyan"]
            self.draw_star(tmp, star_x, star_y, deco["size"], star_color)

        # 文字描边（粗黑轮廓）
        stroke_color = TOY_COLORS["dark_text"]
        for ox in (-2, 0, 2):
            for oy in (-2, 0, 2):
                if ox == 0 and oy == 0:
                    continue
                stroke_surf = font.render(self.text, True, stroke_color)
                tmp.blit(stroke_surf, (canvas_w / 2 - tw / 2 + ox,
                                       canvas_h / 2 - th / 2 + oy))

        # 主体文字
        tmp.blit(text_surf, (canvas_w / 2 - tw / 2, canvas_h / 2 - th / 2))

        # 缩放 + 旋转
        scaled = pygame.transform.scale_by(tmp, self.scale.x)
        rotated = pygame.transform.rotate(scaled, math.degrees(self.rotation))
        draw_pos = pygame.Vector2(self.cx, float_y) - pygame.Vector2(rotated.get_size()) / 2
        surface.blit(rotated, draw_pos)


class TerrainDragTool:
    """左侧工具栏地形拖拽组件，拖拽到画布生成节点。

    纯 Pygame 几何图形渲染，不依赖外部图片素材。
    点击并拖拽地形色块，释放到画布空白处创建新节点，
    释放到已有节点上可切换地形。
    """

    def __init__(self, x, y, terrain_key, color, symbol="", name="",
                 width=64, height=56):
        self.rect = pygame.Rect(x, y, width, height)
        self.terrain_key = terrain_key
        self.color = color
        self.symbol = symbol
        self.name = name
        self.dragging = False
        self._hover = False

    def handle_event(self, event):
        """处理事件，返回 None / terrain_key(开始拖拽) / ('drop', key, mx, my)(释放)。"""
        if event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            self._hover = self.rect.collidepoint(mx, my)
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.rect.collidepoint(mx, my):
                self.dragging = True
                return self.terrain_key  # 信号：开始拖拽

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False
                mx, my = event.pos
                return ("drop", self.terrain_key, mx, my)  # 信号：释放

        return None

    def draw(self, surface):
        """绘制地形色块 + 地形图标 + 悬浮/选中高亮。"""
        border = get_border_color(self.color)

        # 圆角矩形背景
        draw_rounded_rect(surface, self.color, self.rect, radius=8)
        # 描边
        pygame.draw.rect(surface, border, self.rect, 2, border_radius=8)

        # 地形图标（缓存blit替代文字渲染）
        from .render_cache import get_cached_terrain
        icon_size = min(self.rect.width, self.rect.height) - 16
        ter_surf = get_cached_terrain(self.terrain_key, target_size=icon_size)
        surface.blit(ter_surf, (self.rect.centerx - ter_surf.get_width() // 2,
                                self.rect.centery - ter_surf.get_height() // 2 - 4))

        # 地形名（小字）
        if self.name:
            name_font = get_font(10, style="chinese")
            display_name = self.name[:4]
            name_surf = name_font.render(display_name, True, (40, 40, 40))
            surface.blit(name_surf, (self.rect.centerx - name_surf.get_width() // 2,
                                     self.rect.bottom - 14))

        # 悬浮高亮边框
        if self._hover or self.dragging:
            pygame.draw.rect(surface, (255, 220, 0), self.rect.inflate(4, 4), 3, border_radius=10)