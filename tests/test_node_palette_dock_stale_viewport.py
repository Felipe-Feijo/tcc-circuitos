# tests/test_node_palette_dock_stale_viewport.py
"""
Regression test for the "palette opens with a horizontal scrollbar" bug.

Root cause: NodePalette._recompute_columns() read self.scroll.viewport().width()
synchronously from inside NodePalette.resizeEvent(). When the window is
maximized while the palette dock is still hidden, and the dock is only shown
afterwards (exactly the app's real flow: dock starts hidden, user later
clicks the "Add" toolbar button), the QScrollArea's internal viewport resize
has not been applied yet at that point. The column count then gets computed
from a stale/wider width than what the viewport actually settles on,
overflowing the grid and forcing a horizontal scrollbar until the user
manually reselects a size tier (which recomputes outside of resizeEvent,
with the viewport already settled).

This only reproduces reliably through the real MainWindow assembly (docks,
toolbars, menus all present) -- a bare NodePalette + QDockWidget in a plain
QMainWindow does not hit the same timing.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.main_window import MainWindow


def _settle():
    # Column recompute is deferred by one event-loop tick; pump a few times
    # to let both the QScrollArea's internal layout and our deferred
    # recompute run.
    for _ in range(3):
        app.processEvents()


def test_palette_has_no_horizontal_overflow_when_opened_after_maximize():
    win = MainWindow()
    palette = win.node_palette

    win.showMaximized()
    _settle()

    win.actions["open_palette"].setChecked(True)
    _settle()

    viewport_width = palette.scroll.viewport().width()
    item_width = palette.SIZE_TIERS[palette.current_tier]["item_width"]
    spacing = 8

    for name, section in palette.sections.items():
        content_width = section.num_columns * (item_width + spacing)
        assert content_width <= viewport_width, (
            f"[{name}] grid content width {content_width} exceeds viewport "
            f"{viewport_width} (cols={section.num_columns}) -- horizontal "
            f"scrollbar would appear"
        )

    assert not palette.scroll.horizontalScrollBar().isVisible()
