"""
游戏全局常量、兵种、地形配置。

此模块定义了所有游戏常量和数据配置，支持从 config.yaml 加载覆盖。
规则出处：TroopWar 完整玩法手册
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# ─── 兵种配置 ───────────────────────────────────────────────
TROOP_DATA: Dict[Any, dict] = {
    "joker": {
        "name": "橡皮鸭", "alias": "Joker-Kwak", "symbol": "JK", "num": None,
        "desc": "王牌，可覆盖任意敌方，也可被任意敌方覆盖，无自身效果"
    },
    1: {
        "name": "小骷髅", "alias": "Skully", "symbol": "SK", "num": 1,
        "desc": "放置后备用堆抽2，手牌≥7仅抽1"
    },
    2: {
        "name": "玩具队长", "alias": "Captain", "symbol": "CP", "num": 2,
        "desc": "放置后获得一次免费额外放置机会"
    },
    3: {
        "name": "重装骑士", "alias": "Jumbo", "symbol": "SH", "num": 3,
        "desc": "清除所有相邻节点敌方顶层单位"
    },
    4: {
        "name": "飞钩船长", "alias": "Hook", "symbol": "HK", "num": 4,
        "desc": "放置忽略总部连通校验规则"
    },
    5: {
        "name": "XB-42", "alias": "XB-42", "symbol": "PL", "num": 5,
        "desc": "随机弃置对手一张手牌"
    },
    6: {
        "name": "独角兽星耀", "alias": "Star", "symbol": "ST", "num": 6,
        "desc": "从己方弃牌堆回收一张到手牌"
    },
    7: {
        "name": "暴龙萝西", "alias": "Roxy", "symbol": "RX", "num": 7,
        "desc": "无兵种特殊效果"
    },
    # --- 第一批扩展兵种 (8~17) ---
    8: {
        "name": "推推比特", "alias": "Bulby", "symbol": "BU", "num": 5,
        "desc": "【推挤】放置在空位，选择相邻敌军向后推1格，无路可退则秒杀"
    },
    9: {
        "name": "磁钩麦格", "alias": "Maggy", "symbol": "MA", "num": 4,
        "desc": "【牵引】放置在连通区，将距离2格内的一名敌军拉近1格"
    },
    10: {
        "name": "魔方库比", "alias": "Kubi", "symbol": "KU", "num": 4,
        "desc": "【换位】放在与敌军相邻的空位，立刻与之互换位置"
    },
    11: {
        "name": "弹弩班迪", "alias": "Bandy", "symbol": "BA", "num": 3,
        "desc": "【穿透】消灭跨越1个节点的直线敌军（隔山打牛，中间须有棋子）"
    },
    12: {
        "name": "回旋闪回", "alias": "Yo-Yo", "symbol": "YY", "num": 6,
        "desc": "【回旋】消灭相邻敌军后，自身回到手牌，该节点变为空地"
    },
    13: {
        "name": "铁甲布鲁特", "alias": "Brutus", "symbol": "BR", "num": 7,
        "desc": "【重装】(被动) 免疫推拉，只能被基础战力>7的单位正面覆盖"
    },
    14: {
        "name": "泥丸", "alias": "Muddy", "symbol": "MD", "num": 2,
        "desc": "【泥沼】(被动) 被覆盖消灭时，该节点地形永久变为泥沼"
    },
    15: {
        "name": "应援琪莉", "alias": "Cheery", "symbol": "CH", "num": 1,
        "desc": "【光环】(被动) 存活时，所有相邻的己方兵种战力临时+3"
    },
    16: {
        "name": "爆弹邦邦", "alias": "Boom-Boom", "symbol": "BB", "num": 8,
        "desc": "【自毁】放置在空节点，消灭所有相邻敌方兵种，随后自身摧毁"
    },
    17: {
        "name": "越野雷克斯", "alias": "Rex", "symbol": "RX", "num": 5,
        "desc": "【飞跃】放置时可无视相隔的1个单位，直接跳到其背后的空节点上"
    },
}

# ─── 地形配置（原版规则）─────────────────────────────────────
TERRAIN_DATA: Dict[str, dict] = {
    "castle_field": {
        "name": "城堡原野", "symbol": "CF", "color": (200, 180, 140),
        "border_color": (100, 80, 60),
        "desc": "放置后，可将己方任意1枚可见兵种召回手牌。"
    },
    "tropical_pool": {
        "name": "热带泳池", "symbol": "TP", "color": (50, 200, 200),
        "border_color": (30, 120, 150),
        "desc": "仅允许偶数编号的兵种放置于此。"
    },
    "city_of_clouds": {
        "name": "云之城", "symbol": "CC", "color": (220, 220, 255),
        "border_color": (140, 150, 170),
        "desc": "放置后从备用牌堆抽1张兵种。"
    },
    "volcanic_jungle": {
        "name": "火山丛林", "symbol": "VJ", "color": (200, 80, 60),
        "border_color": (120, 30, 20),
        "desc": "放置后，可将相邻的1枚敌方兵种移动到其相邻基地（忽略放置规则）。"
    },
    "cursed_cemetery": {
        "name": "诅咒墓地", "symbol": "CY", "color": (100, 70, 110),
        "border_color": (140, 130, 160),
        "desc": "放置后，从己方弃牌堆选择1枚兵种放入手牌。"
    },
    "caribbean_sea": {
        "name": "加勒比海", "symbol": "CS", "color": (0, 150, 200),
        "border_color": (100, 150, 200),
        "desc": "非对称地形：蓝方2个HQ，红方1个HQ。"
    },
    "station_metalx": {
        "name": "金属X站", "symbol": "MX", "color": (180, 180, 180),
        "border_color": (70, 70, 80),
        "desc": "放置兵种时不触发兵种效果。"
    },
    "battlefield": {
        "name": "战场", "symbol": "BF", "color": (160, 140, 100),
        "border_color": (80, 50, 40),
        "desc": "放置后，选择敌方1张手牌面朝下放置，该回合禁用，下回合归还。"
    },
    "normal": {
        "name": "普通据点", "symbol": "NM", "color": (100, 100, 100),
        "desc": "无任何放置、触发效果"
    },
    "mud": {
        "name": "泥沼", "symbol": "MD", "color": (140, 100, 50),
        "border_color": (80, 50, 20),
        "desc": "黏土怪亡语产生的地形，不可放置兵种；位于此的兵种免疫位移效果。"
    },
}

# ─── 游戏全局常量（默认值，可被 config.yaml 覆盖）──────────
HAND_MAX = 8
TROOP_PER_KIND = 3  # TODO: review - currently unused in game logic
REMOVE_COUNT_PER_GAME = 4
INIT_DRAW_FIRST = 3
INIT_DRAW_SECOND = 4

# ─── Pygame 窗口配置 ──────────────────────────────────────
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800
FPS = 60
HAND_CARD_W = 70
HAND_CARD_H = 110
HAND_TROOP_ICON_SIZE = 64    # 手牌兵种图标大小（原48→64放大）
NODE_RADIUS = 32  # TODO: review - unused, logic uses NODE_RENDER_RADIUS

# ─── 圆角方形地块参数 ──────────────────────────────────────
TILE_SQUARE_SIZE = 72        # 圆角方块整体像素尺寸（世界单位）
TILE_ROUND_RADIUS = 10       # 圆角大小，10-14区间，越大越圆
TILE_PADDING = 4             # 方块内部内边距，地形贴图向内收缩
DRAW_NODE_CIRCLE_OUTLINE = False  # TODO: review - unused in rendering

# ─── 节点半径拆分（视觉/点击/编辑器独立） ──────────────────
NODE_RENDER_RADIUS = TILE_SQUARE_SIZE // 2   # 画面显示半径（=36）
NODE_CLICK_RADIUS = TILE_SQUARE_SIZE // 2    # 鼠标点击判定半径（=36，AABB）
EDITOR_NODE_RADIUS = 36     # 编辑器绘制半径
MIN_NODE_GAP = 80  # TODO: review - unused, map gen uses MIN_NODE_DISTANCE

PLAYER_COLORS: Dict[str, Tuple[int, int, int]] = {
    "red": (235, 110, 110),     # 浅红阵营（原(200,30,30)高饱和→柔和淡红）
    "blue": (100, 145, 230),    # 浅蓝阵营（原(30,60,200)高饱和→柔和淡蓝）
}

# ─── 阵营占领底色半透明值 ──────────────────────────────────
TEAM_BG_ALPHA = 70  # 地块占领底色透明度，避免盖住地形贴图

# ─── 便捷颜色常量 ──────────────────────────────────────────
RED = PLAYER_COLORS["red"]
BLUE = PLAYER_COLORS["blue"]
BG_COLOR = (30, 30, 40)
HAND_Y = 650

# ─── 兵种颜色映射（用于手牌渲染）──────────────────────────────
TROOP_COLOR: Dict[Any, Tuple[int, int, int]] = {
    "joker": (255, 215, 0),
    1: (180, 220, 180),
    2: (100, 180, 100),
    3: (80, 130, 200),
    4: (200, 160, 80),
    5: (160, 120, 200),
    6: (220, 180, 100),
    7: (200, 80, 80),
    # --- 扩展兵种颜色 ---
    8: (139, 119, 101),    # 推推比特 - 土褐色
    9: (180, 180, 220),    # 磁钩麦格 - 银蓝
    10: (100, 200, 220),   # 魔方库比 - 冰蓝
    11: (160, 140, 100),   # 弹弩班迪 - 暗金
    12: (220, 100, 180),   # 回旋闪回 - 粉红
    13: (120, 120, 140),   # 铁甲布鲁特 - 钢灰
    14: (140, 180, 80),    # 泥丸 - 苔绿
    15: (255, 200, 80),    # 应援琪莉 - 亮金
    16: (220, 60, 60),     # 爆弹邦邦 - 烈红
    17: (80, 200, 160),    # 越野雷克斯 - 翠绿
}

# ─── 兵种列表（用于校验）───────────────────────────────────
TROOP_LIST: List[Any] = list(TROOP_DATA.keys())

# ─── 地形列表（用于编辑器快捷键）──────────────────────────
TERRAIN_LIST: List[str] = list(TERRAIN_DATA.keys())

# ─── 地形权重（用于地图生成）──────────────────────────────
TERRAIN_WEIGHTS: Dict[str, float] = {
    "normal": 0.35,
    "castle_field": 0.10,
    "tropical_pool": 0.08,
    "city_of_clouds": 0.08,
    "volcanic_jungle": 0.08,
    "cursed_cemetery": 0.08,
    "caribbean_sea": 0.05,
    "station_metalx": 0.08,
    "battlefield": 0.10,
    "mud": 0.00,  # 仅由黏土怪亡语产生，不在随机池中
}

# ─── 地图生成默认参数 ─────────────────────────────────────
MAP_NODE_COUNT = 25
MAP_EDGE_RADIUS = 0.30
MAP_WIDTH = 1200.0
MAP_HEIGHT = 700.0

# ─── 星星计分胜利目标 ─────────────────────────────────────
STAR_WIN_GOAL = 4   # 集齐星星数获胜

# ─── 地形颜色映射 ─────────────────────────────────────────
TERRAIN_COLOR: Dict[str, Tuple[int, int, int]] = {
    k: v["color"] for k, v in TERRAIN_DATA.items()
}

# ─── 地形符号映射 ─────────────────────────────────────────
TERRAIN_SYM: Dict[str, str] = {
    k: v["symbol"] for k, v in TERRAIN_DATA.items()
}

# ─── 旧地形键名别名映射（向后兼容）────────────────────────
TERRAIN_KEY_ALIASES: Dict[str, str] = {
    "cloud_castle": "city_of_clouds",
    "ancient_battlefield": "battlefield",
    "metal_station_x": "station_metalx",
    "cursed_graveyard": "cursed_cemetery",
    "glue": "mud",  # 向后兼容：旧键名映射到新键名
}


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """从 config.yaml 加载配置，覆盖默认常量。

    Args:
        config_path: 配置文件路径，默认为项目根目录下的 config.yaml

    Returns:
        解析后的配置字典
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def apply_config(cfg: Dict[str, Any]) -> None:
    """将配置字典应用到全局常量。

    Args:
        cfg: 由 load_config() 返回的配置字典
    """
    global HAND_MAX, TROOP_PER_KIND, REMOVE_COUNT_PER_GAME
    global INIT_DRAW_FIRST, INIT_DRAW_SECOND
    global SCREEN_WIDTH, SCREEN_HEIGHT, FPS
    global HAND_CARD_W, HAND_CARD_H, NODE_RADIUS, PLAYER_COLORS
    global NODE_RENDER_RADIUS, NODE_CLICK_RADIUS, EDITOR_NODE_RADIUS, MIN_NODE_GAP
    global TILE_SQUARE_SIZE, TILE_ROUND_RADIUS, TILE_PADDING, HAND_TROOP_ICON_SIZE
    global STAR_WIN_GOAL

    game_cfg = cfg.get("game", {})
    HAND_MAX = game_cfg.get("hand_max", HAND_MAX)
    TROOP_PER_KIND = game_cfg.get("troop_per_kind", TROOP_PER_KIND)
    REMOVE_COUNT_PER_GAME = game_cfg.get("remove_count_per_game", REMOVE_COUNT_PER_GAME)
    INIT_DRAW_FIRST = game_cfg.get("init_draw_first", INIT_DRAW_FIRST)
    INIT_DRAW_SECOND = game_cfg.get("init_draw_second", INIT_DRAW_SECOND)
    STAR_WIN_GOAL = game_cfg.get("star_win_goal", STAR_WIN_GOAL)

    screen_cfg = cfg.get("screen", {})
    SCREEN_WIDTH = screen_cfg.get("width", SCREEN_WIDTH)
    SCREEN_HEIGHT = screen_cfg.get("height", SCREEN_HEIGHT)
    FPS = screen_cfg.get("fps", FPS)
    HAND_CARD_W = screen_cfg.get("hand_card_w", HAND_CARD_W)
    HAND_CARD_H = screen_cfg.get("hand_card_h", HAND_CARD_H)
    HAND_TROOP_ICON_SIZE = screen_cfg.get("hand_troop_icon_size", HAND_TROOP_ICON_SIZE)
    NODE_RADIUS = screen_cfg.get("node_radius", NODE_RADIUS)
    NODE_RENDER_RADIUS = screen_cfg.get("node_render_radius", NODE_RENDER_RADIUS)
    NODE_CLICK_RADIUS = screen_cfg.get("node_click_radius", NODE_CLICK_RADIUS)
    EDITOR_NODE_RADIUS = screen_cfg.get("editor_node_radius", EDITOR_NODE_RADIUS)
    MIN_NODE_GAP = screen_cfg.get("min_node_gap", MIN_NODE_GAP)
    TILE_SQUARE_SIZE = screen_cfg.get("tile_square_size", TILE_SQUARE_SIZE)
    TILE_ROUND_RADIUS = screen_cfg.get("tile_round_radius", TILE_ROUND_RADIUS)
    TILE_PADDING = screen_cfg.get("tile_padding", TILE_PADDING)

    color_cfg = cfg.get("player_colors", {})
    for key in ("red", "blue"):
        if key in color_cfg:
            PLAYER_COLORS[key] = tuple(color_cfg[key])