from pathlib import Path
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QGraphicsItem
from PyQt6.QtCore import Qt
from editor.clipboard_manager import ClipboardManager
from editor.delete_manager import DeleteManager
from editor.editor_controller import EditorController
from graphics.items.base.diagram_item_base import DiagramItemBase
from graphics.scene import GraphicsScene
from main_window.ui.docks.node_palette_dock import create_node_palette
from graphics.items.base.nodes.node_item import NodeItem

from graphics.view import GraphicsView
from simulation.simulation_session import SimulationSession
from persistence.file_session import SceneFileSession

from .actions import create_actions
from .ui.menus import create_menus
from .ui.toolbars import create_toolbars

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Simulador – Editor Gráfico")

        self.current_file: str | None = None

        self._init_state()
        self._init_editor()

        self.simulation = SimulationSession(self.scene)
        self.file_session = SceneFileSession(self.scene, self)

        self._init_node_palette()
        self._init_actions_ui()


        

    def _init_state(self):
        self.mode = None
        self.pending_node = None
        self.active_context_menu = None
        self.hover_anchor = None

    def _init_editor(self):
        self.scene = GraphicsScene()
        self.editor_controller = EditorController(self.scene)
        self.delete_manager = DeleteManager(self.scene)
        self.clipboard_manager = ClipboardManager()

        self.view = GraphicsView(self, self.scene)
        self.setCentralWidget(self.view)

    def _init_node_palette(self):
        self.node_palette, self.palette_dock = create_node_palette(self)

    def _init_actions_ui(self):
        self.actions = create_actions(self)
        create_menus(self, self.actions)
        create_toolbars(self, self.actions)

        # estado inicial explícito
        self.actions["mode_select"].setChecked(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_current_mode()
            event.accept()
            return

        super().keyPressEvent(event)

    def cancel_current_mode(self):
        # 1. modo lógico
        self.set_mode(None)
        self.pending_node = None

        # 2. sincroniza ações (UI)
        self.actions["mode_select"].setChecked(True)

        # 3. fecha UI de adição
        self.palette_dock.hide()
        self.actions["open_palette"].setChecked(False)

        self.view.cleanup_temp_connection()
        self.view.cleanup_node_preview()

        self.view.unsetCursor()

    def new_scene(self):
        self.set_mode(None)
        self.scene = GraphicsScene()
        self.view.setScene(self.scene)
        self.simulation = SimulationSession(self.scene)
        self.file_session = SceneFileSession(self.scene, self)
        self.setWindowTitle("Simulador – Editor Gráfico")
        self.update_scene_rect()


    def set_mode(self, mode: str | None, node_cls=None):
        self.mode = mode
        self.view.cleanup_node_preview()
        self.pending_node = node_cls

        if mode != "add":
            self.node_palette.clear_selection()

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

        if mode == "simulate":
            self.start_simulation()
        else:
            self.stop_simulation()

        self._update_mode_actions(mode)
        self.update_simulation_actions()

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


    def add_node_at(self, x, y):
        if not self.pending_node:
            return

        item = self.pending_node(sensor_registry=self.scene.sensor_registry)
        item.editor = self

        w = item.boundingRect().width()
        h = item.boundingRect().height()

        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        item.setPos(x - w / 2, y - h / 2)

        self.scene.addItem(item)
        self.update_scene_rect()
        self.set_mode(None)

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
        # UI concern
        if self.active_context_menu:
            self.active_context_menu.close()
            self.active_context_menu = None

        # domain/editor concern
        deleted = self.delete_manager.delete_selection()

        if deleted:
            self.update_scene_rect()

    def toggle_node_palette(self, checked):
        self.palette_dock.setVisible(checked)

    def start_simulation(self):
        self.simulation.start()
        self.simulation.controller.state_changed.connect(self.update_simulation_actions)

    def stop_simulation(self):
        self.simulation.stop()

    def save_scene(self):
        self.file_session.save()

    def save_scene_as(self):
        self.file_session.save_as()

    def open_scene(self):
        self.set_mode(None)
        self.file_session.open()

    def toggle_play(self):
        if self.mode != "simulate":
            self.set_mode("simulate")

        self.simulation.toggle_play()
        self.update_simulation_actions()

    def on_step_back(self):
        if self.simulation.controller.step_backward():
            self.update_simulation_actions()


    def on_step_forward(self):
        if self.simulation.controller.step_forward():
            self.update_simulation_actions()

    def update_simulation_actions(self):
        run = self.actions["run"]
        step_back = self.actions["step_back"]
        step_fwd = self.actions["step_forward"]

        # fora do modo simulate → tudo apagado
        if self.mode != "simulate" or not self.simulation or not self.simulation.active:
            run.setEnabled(False)
            run.setText("Run")
            step_back.setEnabled(False)
            step_fwd.setEnabled(False)
            return

        ctrl = self.simulation.controller

        # Run / Pause
        run.setEnabled(True)
        run.setText("Pause" if ctrl.playing else "Run")

        # Steps só quando pausado
        steps_enabled = not ctrl.playing

        step_back.setEnabled(
            steps_enabled and ctrl.can_step_back()
        )

        step_fwd.setEnabled(
            steps_enabled
        )

    def _update_mode_actions(self, active_mode):
        for action in self.mode_group.actions():
            action.setChecked(action.data() == active_mode)