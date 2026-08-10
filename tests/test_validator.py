"""
数据校验层测试。

覆盖：
- 兵种数据校验
- 地形数据校验
- 节点数据校验
- 放置操作校验
- 抽卡操作校验
"""

import pytest
from pydantic import ValidationError

from ..game.validator import (
    TroopData, TerrainData, NodeData,
    PlaceAction, DrawAction, GameStateSnapshot,
    validate_place_action, validate_draw_action, validate_node_data,
)


class TestTroopData:
    """兵种数据校验测试。"""

    def test_valid_troop_joker(self):
        t = TroopData(troop_key="joker")
        assert t.troop_key == "joker"

    def test_valid_troop_number(self):
        t = TroopData(troop_key=3, value=3)
        assert t.troop_key == 3
        assert t.value == 3

    def test_invalid_troop_key(self):
        with pytest.raises(ValidationError):
            TroopData(troop_key="unknown_troop")

    def test_joker_value_none(self):
        """Joker 无战力值。"""
        t = TroopData(troop_key="joker")
        assert t.value is None


class TestTerrainData:
    """地形数据校验测试。"""

    def test_valid_terrain(self):
        t = TerrainData(name="normal")
        assert t.name == "normal"

    def test_valid_special_terrain(self):
        t = TerrainData(name="castle_field")
        assert t.name == "castle_field"

    def test_invalid_terrain(self):
        with pytest.raises(ValidationError):
            TerrainData(name="mars")


class TestNodeData:
    """节点数据校验测试。"""

    def test_valid_node(self):
        n = NodeData(nid=0, x=100, y=200, terrain="normal")
        assert n.nid == 0

    def test_invalid_terrain(self):
        with pytest.raises(ValidationError):
            NodeData(nid=0, x=100, y=200, terrain="invalid")

    def test_invalid_owner(self):
        with pytest.raises(ValidationError):
            NodeData(nid=0, x=100, y=200, owner="green")

    def test_node_with_troop(self):
        n = validate_node_data(nid=1, x=100, y=200, troop_key=5, troop_value=5, owner="red")
        assert n.troop is not None
        assert n.troop.troop_key == 5


class TestPlaceAction:
    """放置操作校验测试。"""

    def test_valid_action(self):
        a = validate_place_action("red", 3, 1)
        assert a.player_color == "red"
        assert a.troop_key == 3

    def test_valid_joker_action(self):
        a = validate_place_action("blue", "joker", 5)
        assert a.troop_key == "joker"

    def test_invalid_color(self):
        with pytest.raises(ValidationError):
            validate_place_action("green", 3, 1)

    def test_invalid_troop(self):
        with pytest.raises(ValidationError):
            validate_place_action("red", "unknown", 1)


class TestDrawAction:
    """抽卡操作校验测试。"""

    def test_valid_draw(self):
        a = validate_draw_action("red", 2)
        assert a.count == 2

    def test_count_out_of_range(self):
        with pytest.raises(ValidationError):
            validate_draw_action("red", 0)
        with pytest.raises(ValidationError):
            validate_draw_action("red", 6)