from PyQt6.QtWidgets import QMainWindow, QGraphicsScene, QGraphicsRectItem, QMessageBox
from graphics.view import GraphicsView
from graphics.items.component_item import ComponentItem

from .actions import create_actions
from .menus import create_menus
from .toolbars import create_toolbars

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Simulador – Editor Gráfico")

        self.scene = QGraphicsScene()
        self.view = GraphicsView(self, self.scene)
        self.setCentralWidget(self.view)

        self.mode = None

        self.actions = create_actions(self)
        create_menus(self, self.actions)
        create_toolbars(self, self.actions)
    
    def new_scene(self):
        self.scene.clear()
        self.update_scene_rect()

    def set_mode(self, mode: str | None):
        self.mode = mode

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
        w, h = 80, 40
        item = ComponentItem(0, 0, w, h)
        item.editor = self

        # centraliza no clique
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
