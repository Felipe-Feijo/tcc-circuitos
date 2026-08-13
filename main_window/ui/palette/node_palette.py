"""Widget da paleta de nós com scroll, seletor de tamanho e organização em seções."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton, QButtonGroup
)
from PyQt6.QtCore import Qt
from main_window.ui.palette.node_palette_item import NodePaletteItem
from main_window.ui.palette.palette_section import PaletteSection
from main_window import settings


class NodePalette(QWidget):
    SIZE_TIERS = {
        "small":  {"pixmap": (60, 40),  "item_width": 100, "font_delta": 0},
        "medium": {"pixmap": (84, 56),  "item_width": 130, "font_delta": 1},
        "large":  {"pixmap": (112, 76), "item_width": 160, "font_delta": 2},
    }
    TIER_LABELS = {"small": "P", "medium": "M", "large": "G"}
    TIER_TOOLTIPS = {"small": "Pequeno", "medium": "Médio", "large": "Grande"}

    def __init__(self, parent=None, settings_obj=None):
        super().__init__(parent)
        self._settings_obj = settings_obj

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(8)
        title = QLabel("Nodes")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # seletor de tamanho (Pequeno / Médio / Grande)
        tier_row = QHBoxLayout()
        tier_row.addStretch()
        self.tier_buttons: dict[str, QPushButton] = {}
        self._tier_group = QButtonGroup(self)
        self._tier_group.setExclusive(True)
        for tier in ("small", "medium", "large"):
            btn = QPushButton(self.TIER_LABELS[tier])
            btn.setObjectName("sizeTierButton")
            btn.setCheckable(True)
            btn.setToolTip(self.TIER_TOOLTIPS[tier])
            btn.clicked.connect(lambda checked, t=tier: self.set_size_tier(t))
            self._tier_group.addButton(btn)
            self.tier_buttons[tier] = btn
            tier_row.addWidget(btn)
        tier_row.addStretch()
        main_layout.addLayout(tier_row)

        # área scrollável
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        main_layout.addWidget(self.scroll)

        self.sections = {}

        # container interno com grid layout
        container = QWidget()
        self.container_layout = QVBoxLayout(container)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.container_layout.setSpacing(8)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(container)

        self.selected_item: NodePaletteItem | None = None

        self.current_tier = settings.get_palette_tier(self._settings_obj)
        if self.current_tier not in self.SIZE_TIERS:
            self.current_tier = settings.DEFAULT_PALETTE_TIER
        self.tier_buttons[self.current_tier].setChecked(True)

    def on_click(self, item, callback):
        self.select_item(item)
        callback()

    def select_item(self, item: NodePaletteItem):
        if self.selected_item is item:
            return
        if self.selected_item:
            self.selected_item.set_selected(False)
        self.selected_item = item
        item.set_selected(True)

    def clear_selection(self):
        if self.selected_item:
            self.selected_item.set_selected(False)
        self.selected_item = None

    def add_section(self, name: str):
        if name in self.sections:
            return self.sections[name]

        section = PaletteSection(name, num_columns=1)
        self.sections[name] = section
        self.container_layout.addWidget(section)
        return section

    def register_item(self, item: NodePaletteItem, callback):
        item.mouseReleaseEvent = lambda e: self.on_click(item, callback)

    def set_size_tier(self, name: str, persist: bool = True):
        if name not in self.SIZE_TIERS:
            return
        self.current_tier = name
        tier = self.SIZE_TIERS[name]
        for section in self.sections.values():
            section.apply_item_size(tier["pixmap"], tier["item_width"], tier["font_delta"])

        self.tier_buttons[name].setChecked(True)

        if persist:
            settings.set_palette_tier(name, self._settings_obj)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute_columns()

    def _recompute_columns(self):
        item_width = self.SIZE_TIERS[self.current_tier]["item_width"]
        spacing = 8
        available_width = self.scroll.viewport().width()
        cols = max(1, available_width // (item_width + spacing))
        for section in self.sections.values():
            section.set_num_columns(cols)
