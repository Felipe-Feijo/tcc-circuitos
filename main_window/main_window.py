from PyQt6.QtWidgets import QMainWindow, QGraphicsScene, QMessageBox, QGraphicsItem, QDockWidget, QToolBar
from PyQt6.QtCore import Qt
from editor.editor_controller import EditorController
from graphics.items.base.diagram_item_base import DiagramItemBase
from graphics.items.base.nodes.node_item import NodeItem
from graphics.utils.pixmap_utils import generate_pixmap_for_palette
from graphics.view import GraphicsView

from graphics.ui.palette.component_palette import ComponentPalette
from graphics.items.factories.home_factory import create_home_component

from .actions import create_actions
from .menus import create_menus
from .toolbars import create_toolbars

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Simulador – Editor Gráfico")

        self.scene = QGraphicsScene()

        self.editor_controller = EditorController(self.scene)
        self.view = GraphicsView(self, self.scene)
        self.setCentralWidget(self.view)

        self.component_palette = ComponentPalette()
        self.palette_dock = QDockWidget("Componentes", self)
        self.palette_dock.setWidget(self.component_palette)
        self.palette_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )

        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea,
            self.palette_dock
        )

        self.component_palette.add_component(
            name="Home",
            pixmap=generate_pixmap_for_palette("resources/components/component_item/home.png"),
            callback=lambda: self.set_mode(
                "add",
                component_factory=create_home_component
            )
        )
        # começa fechado
        self.palette_dock.hide()

        self.mode = None
        self.active_context_menu = None
        self.pending_component = None

        self.actions = create_actions(self)
        create_menus(self, self.actions)
        create_toolbars(self, self.actions)

        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_current_mode()
            event.accept()
            return

        super().keyPressEvent(event)

    def cancel_current_mode(self):
        self.set_mode(None)  # modo seleção padrão

        # limpa fábrica pendente
        self.pending_component = None

        # opcional: fecha a palette
        if self.palette_dock.isVisible():
            self.palette_dock.hide()

    def new_scene(self):
        self.scene.clear()
        self.update_scene_rect()


    def set_mode(self, mode: str | None, component_factory=None):
        self.mode = mode
        self.pending_component = component_factory

        # sincroniza UI
        if mode is None:
            self.actions["mode_select"].setChecked(True)
        elif mode == "add":
            self.actions["open_palette"].setChecked(True)
        elif mode == "connect":
            self.actions["mode_connect"].setChecked(True)

        is_select_mode = (mode is None)

        for item in self.scene.items():
            # Tudo no diagrama pode ser selecionado
            if isinstance(item, DiagramItemBase):
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                    is_select_mode
                )

            # Só nós podem ser movidos
            if isinstance(item, NodeItem):
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                    is_select_mode
                )

    def zoom_in(self):
        self.view.zoom_in()

    def zoom_out(self):
        self.view.zoom_out()

    def zoom_to_contents(self):
        self.view.zoom_to_contents()

    def show_about(self):
        QMessageBox.about(
            self,
            "About",
            "Simulador – Editor Gráfico\n"
            "Pneumatic and Hydraulic Systems\n\n"
            "Built with PyQt6"
        )


    def add_component_at(self, x, y):
        if not self.pending_component:
            return

        item = self.pending_component(self)

        w = item.boundingRect().width()
        h = item.boundingRect().height()

        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        item.setPos(x - w / 2, y - h / 2)

        self.scene.addItem(item)
        self.update_scene_rect()

    def update_scene_rect(self):
        view = self.view

        # Área visível atual (viewport → scene)
        visible_rect = view.mapToScene(
            view.viewport().rect()
        ).boundingRect()

        # Área ocupada pelos itens
        items_rect = self.scene.itemsBoundingRect()

        # Se não houver itens ainda
        if items_rect.isNull():
            self.scene.setSceneRect(visible_rect)
            return

        # Margem razoável (10% da maior dimensão visível)
        margin = max(
            80,
            max(visible_rect.width(), visible_rect.height()) * 0.1
        )

        # União da área visível com os itens
        united = visible_rect.united(items_rect)

        self.scene.setSceneRect(
            united.adjusted(-margin, -margin, margin, margin)
        )

    def delete_selected_items(self):

        if self.active_context_menu is not None:
            self.active_context_menu.close()
            self.active_context_menu = None

        self.delete_items(self.scene.selectedItems())

    def delete_items(self, items):
        if not items:
            return

        scene = self.scene

        for item in items:
            if hasattr(item, "prepare_delete"):
                item.prepare_delete()
            scene.removeItem(item)

        self.update_scene_rect()

    def toggle_component_palette(self, checked):
        self.palette_dock.setVisible(checked)