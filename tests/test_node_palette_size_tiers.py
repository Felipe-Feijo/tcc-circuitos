# tests/test_node_palette_size_tiers.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from PyQt6.QtCore import QSettings
from main_window.ui.palette.node_palette import NodePalette

ICON_PATH = "resources/nodes/accumulator/accumulator.png"


def _ini_settings(tmp_path):
    return QSettings(str(tmp_path / "test_settings.ini"), QSettings.Format.IniFormat)


def test_default_tier_is_medium(tmp_path):
    # Isolated QSettings: a NodePalette() with no explicit settings_obj
    # would otherwise read whatever tier is persisted in the real
    # per-user store (e.g. after actually using the app), making this
    # test flaky/order-dependent across machines and runs.
    palette = NodePalette(settings_obj=_ini_settings(tmp_path))
    assert palette.current_tier == "medium"
    assert palette.tier_buttons["medium"].isChecked()


def test_set_size_tier_resizes_existing_items(tmp_path):
    palette = NodePalette(settings_obj=_ini_settings(tmp_path))
    section = palette.add_section("Hydraulic")
    item = section.add_node("Accumulator", ICON_PATH, callback=lambda: None)

    palette.set_size_tier("large")

    assert palette.current_tier == "large"
    assert item.width() == NodePalette.SIZE_TIERS["large"]["item_width"]
    assert palette.tier_buttons["large"].isChecked()
    assert not palette.tier_buttons["medium"].isChecked()


def test_clicking_tier_button_switches_tier(tmp_path):
    palette = NodePalette(settings_obj=_ini_settings(tmp_path))
    palette.tier_buttons["small"].click()
    assert palette.current_tier == "small"


def test_set_size_tier_persists(tmp_path):
    s = _ini_settings(tmp_path)
    palette = NodePalette(settings_obj=s)

    palette.set_size_tier("large")

    from main_window import settings
    assert settings.get_palette_tier(s) == "large"


def test_set_size_tier_recomputes_columns(tmp_path):
    palette = NodePalette(settings_obj=_ini_settings(tmp_path))
    palette.show()
    section = palette.add_section("Hydraulic")
    section.add_node("Accumulator", ICON_PATH, callback=lambda: None)

    palette.resize(600, 400)
    app.processEvents()

    palette.set_size_tier("small")
    small_cols = section.num_columns

    palette.set_size_tier("large")
    app.processEvents()
    large_cols = section.num_columns

    assert large_cols != small_cols


def test_apply_size_tracks_live_app_font(tmp_path):
    palette = NodePalette(settings_obj=_ini_settings(tmp_path))
    section = palette.add_section("Hydraulic")
    item = section.add_node("Accumulator", ICON_PATH, callback=lambda: None)

    original_font = app.font()
    try:
        new_font = app.font()
        new_font.setPointSize(original_font.pointSize() + 9)
        app.setFont(new_font)

        palette.set_size_tier("large")

        expected = app.font().pointSize() + NodePalette.SIZE_TIERS["large"]["font_delta"]
        assert item.text_label.font().pointSize() == expected
    finally:
        app.setFont(original_font)
