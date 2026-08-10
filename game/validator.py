"""
Pydantic 数据校验层。

对游戏核心数据结构进行运行时校验，防止非法状态传播。
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator

from .constants import TROOP_LIST, TERRAIN_LIST


class TroopData(BaseModel):
    """兵种数据校验。"""
    troop_key: str | int
    alias: str = ""
    value: int | None = Field(default=None, ge=1, le=10)

    @field_validator("troop_key")
    @classmethod
    def key_must_be_valid(cls, v):
        if v not in TROOP_LIST:
            raise ValueError(f"未知兵种键: {v}，合法值: {TROOP_LIST}")
        return v


class TerrainData(BaseModel):
    """地形数据校验。"""
    name: str
    color: tuple[int, int, int] = Field(default=(200, 200, 200))
    sym: str = ""

    @field_validator("name")
    @classmethod
    def name_must_be_valid(cls, v: str) -> str:
        if v not in TERRAIN_LIST:
            raise ValueError(f"未知地形: {v}，合法值: {TERRAIN_LIST}")
        return v


class NodeData(BaseModel):
    """棋盘节点数据校验。"""
    nid: int = Field(ge=0)
    x: float
    y: float
    terrain: str = "normal"
    troop: Optional[TroopData] = None
    owner: Optional[str] = None

    @field_validator("terrain")
    @classmethod
    def terrain_must_be_valid(cls, v: str) -> str:
        if v not in TERRAIN_LIST:
            raise ValueError(f"未知地形: {v}")
        return v

    @field_validator("owner")
    @classmethod
    def owner_must_be_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("red", "blue"):
            raise ValueError(f"owner 必须为 red/blue/null，得到: {v}")
        return v


class PlaceAction(BaseModel):
    """放置兵种操作校验。"""
    player_color: str
    troop_key: str | int
    target_nid: int = Field(ge=0)

    @field_validator("player_color")
    @classmethod
    def color_must_be_valid(cls, v: str) -> str:
        if v not in ("red", "blue"):
            raise ValueError(f"玩家颜色必须为 red/blue，得到: {v}")
        return v

    @field_validator("troop_key")
    @classmethod
    def troop_must_be_valid(cls, v):
        if v not in TROOP_LIST:
            raise ValueError(f"未知兵种键: {v}")
        return v


class DrawAction(BaseModel):
    """抽卡操作校验。"""
    player_color: str
    count: int = Field(default=1, ge=1, le=5)

    @field_validator("player_color")
    @classmethod
    def color_must_be_valid(cls, v: str) -> str:
        if v not in ("red", "blue"):
            raise ValueError(f"玩家颜色必须为 red/blue，得到: {v}")
        return v


class GameStateSnapshot(BaseModel):
    """游戏状态快照校验。"""
    current_player: str
    red_hand_size: int = Field(ge=0)
    blue_hand_size: int = Field(ge=0)
    red_deck_size: int = Field(ge=0)
    blue_deck_size: int = Field(ge=0)
    nodes_count: int = Field(ge=0)
    turn_number: int = Field(ge=0)
    game_over: bool = False

    @field_validator("current_player")
    @classmethod
    def player_must_be_valid(cls, v: str) -> str:
        if v not in ("red", "blue"):
            raise ValueError(f"当前玩家必须为 red/blue，得到: {v}")
        return v


def validate_place_action(player_color: str, troop_key: str | int, target_nid: int) -> PlaceAction:
    """校验放置操作，失败时抛出 ValueError。"""
    return PlaceAction(
        player_color=player_color,
        troop_key=troop_key,
        target_nid=target_nid,
    )


def validate_draw_action(player_color: str, count: int = 1) -> DrawAction:
    """校验抽卡操作，失败时抛出 ValueError。"""
    return DrawAction(player_color=player_color, count=count)


def validate_node_data(nid: int, x: float, y: float, terrain: str = "normal",
                       troop_key: str | int | None = None, troop_value: int | None = None,
                       owner: str | None = None) -> NodeData:
    """校验节点数据，失败时抛出 ValueError。"""
    troop = None
    if troop_key is not None:
        troop = TroopData(troop_key=troop_key, value=troop_value)
    return NodeData(nid=nid, x=x, y=y, terrain=terrain, troop=troop, owner=owner)