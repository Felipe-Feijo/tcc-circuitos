"""Cria o QDockWidget flutuante que contém a paleta de nós."""

from editor.mode import EditorMode
from PyQt6.QtWidgets import QDockWidget
from PyQt6.QtCore import Qt
from main_window.ui.palette.node_palette import NodePalette
from main_window.ui.registry.node_registry import register_nodes
from main_window import settings


def create_node_palette(main_window):
    palette = NodePalette()
    palette.set_size_tier(settings.get_palette_tier(), persist=False)

    palette.add_section("Pneumatic")
    palette.add_section("Electric")
    palette.add_section("Hydraulic")

    dock = QDockWidget("Nodes", main_window)
    dock.setMinimumWidth(180)
    dock.setMaximumWidth(700)
    dock.setWidget(palette)
    dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea |
        Qt.DockWidgetArea.RightDockWidgetArea
    )

    main_window.addDockWidget(
        Qt.DockWidgetArea.LeftDockWidgetArea,
        dock
    )

    dock.hide()

    register_nodes(palette, lambda node_desc: main_window.set_mode(EditorMode.ADD, node_desc=node_desc))
    palette.set_size_tier(palette.current_tier, persist=False)  # re-apply to newly-registered items

    if hasattr(main_window, "state"):
        main_window.state.theme_changed.connect(palette.set_light_theme)

    return palette, dock
