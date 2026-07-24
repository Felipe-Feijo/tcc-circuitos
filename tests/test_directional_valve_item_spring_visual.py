import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from graphics.items.base.nodes.directional_valve.valve_4_3_ways import Valve_4_3_Ways


def test_two_position_item_has_no_spring_visuals():
    item = Valve_4_2_Ways(domain="pneumatic")
    assert item.spring_visuals == {}


def test_three_position_item_has_spring_visuals_both_sides():
    item = Valve_4_3_Ways(domain="pneumatic")
    assert set(item.spring_visuals.keys()) == {"left", "right"}
    for side in ("left", "right"):
        visuals = item.spring_visuals[side]
        assert isinstance(visuals["active"], QPixmap)
        assert isinstance(visuals["inactive"], QPixmap)
        assert not visuals["active"].isNull()
        assert not visuals["inactive"].isNull()


def test_spring_sprite_scaled_down_50_percent():
    item = Valve_4_3_Ways(domain="pneumatic")
    full = QPixmap("resources/actuators/spring/spring_active.png")
    scaled = item.spring_visuals["left"]["active"]
    assert abs(scaled.width() - round(full.width() * 0.5)) <= 1
    assert abs(scaled.height() - round(full.height() * 0.5)) <= 1


def test_spring_pixmap_swaps_with_bit_state():
    item = Valve_4_3_Ways(domain="pneumatic")
    item.bits["left"] = 0
    inactive = item._spring_pixmap_for("left")
    item.bits["left"] = 1
    active = item._spring_pixmap_for("left")
    assert active is item.spring_visuals["left"]["active"]
    assert inactive is item.spring_visuals["left"]["inactive"]


def test_spring_rects_positioned_above_body_flush_to_each_side():
    item = Valve_4_3_Ways(domain="pneumatic")
    left_rect = item.spring_rects["left"]
    right_rect = item.spring_rects["right"]
    assert left_rect.right() == 0        # encostada na borda esquerda do body
    assert right_rect.left() == item.width  # encostada na borda direita do body
    # a mola fica sobreposta à parte superior do body -- 1/3 acima do topo
    # (y<0), o resto dentro do body (bottom > 0)
    assert left_rect.top() < 0
    assert right_rect.top() < 0
    assert left_rect.bottom() == left_rect.height() * 2 / 3
    assert right_rect.bottom() == right_rect.height() * 2 / 3


def test_bounding_rect_covers_spring_extent_above_body():
    item = Valve_4_3_Ways(domain="pneumatic")
    spring_top = min(rect.top() for rect in item.spring_rects.values())
    bounds = item.boundingRect()
    assert bounds.top() <= spring_top
