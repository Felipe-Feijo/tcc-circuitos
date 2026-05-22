"""Cria o QDockWidget flutuante que contém a paleta de nós."""

from editor.mode import EditorMode
from PyQt6.QtWidgets import QDockWidget
from editor.mode import EditorMode
from PyQt6.QtCore import Qt
from main_window.ui.palette.node_palette import NodePalette
from main_window.ui.registry.node_registry import register_nodes


def create_node_palette(main_window):
    palette = NodePalette()

    palette.add_section("Pneumatic")
    palette.add_section("Electric")
    palette.add_section("Hydraulic")

    dock = QDockWidget("Nodes", main_window)
    dock.setFixedWidth(260)
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

    return palette, dock