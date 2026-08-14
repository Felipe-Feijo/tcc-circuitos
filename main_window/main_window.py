"""Janela principal da aplicação: monta e conecta todos os subsistemas."""

from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QGraphicsItem
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from main_window import theme
from editor.clipboard_manager import ClipboardManager
from editor.editor_state import EditorState
from editor.mode import EditorMode
from editor.delete_manager import DeleteManager
from editor.editor_controller import EditorController
from graphics.items.base.diagram_item_base import DiagramItemBase
from graphics.scene import GraphicsScene
from main_window.ui.docks.node_palette_dock import create_node_palette
from main_window import settings
from graphics.items.base.nodes.node_item import NodeItem
from graphics.labels.label import LabelItem

from graphics.view import GraphicsView
from simulation.simulation_session import SimulationSession
from persistence.file_session import SceneFileSession

from .actions import create_actions
from .ui.menus import create_menus
from .ui.toolbars import create_toolbars

from .actions.simulation_actions import SPEED_STEPS  # ajusta o import conforme sua estrutura

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        


        self.setWindowTitle("Simulador – Editor Gráfico")

        self.current_file: str | None = None

        self.state = EditorState()
        self._init_editor()

        self.simulation = SimulationSession(self.scene)
        self.file_session = SceneFileSession(self.scene, self, self.state)

        self._init_node_palette()
        self._init_actions_ui()
        self._wire_state_callbacks()

        self.set_light_theme(False)


        

    def _init_editor(self):
        self.scene = GraphicsScene()
        self.editor_controller = EditorController(self.scene)
        self.delete_manager = DeleteManager(self.scene)
        self.clipboard_manager = ClipboardManager()

        self.view = GraphicsView(self.state, self.scene)
        self.setCentralWidget(self.view)

    def _init_node_palette(self):
        self.node_palette, self.palette_dock = create_node_palette(self)

    def _init_actions_ui(self):
        self.actions = create_actions(self)
        create_menus(self, self.actions)
        create_toolbars(self, self.actions)

        # Registra todas as ações na janela para que os atalhos
        # ApplicationShortcut funcionem mesmo fora de menus (necessário no Windows)
        for action in self.actions.values():
            self.addAction(action)

        # estado inicial explícito
        self.actions["mode_select"].setChecked(True)

    def _wire_state_callbacks(self):
        # Disconnect first to avoid duplicate connections on new_scene()
        try:
            self.state.add_node_requested.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            self.state.scene_rect_update_requested.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.state.add_node_requested.connect(self.add_node_at)
        self.state.scene_rect_update_requested.connect(self.update_scene_rect)
        self.state.actions = self.actions

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_current_mode()
            event.accept()
            return

        super().keyPressEvent(event)

    def cancel_current_mode(self):
        # 1. modo lógico
        self.set_mode(EditorMode.SELECT)
        self.state.pending_node = None

        # 2. sincroniza ações (UI)
        self.actions["mode_select"].setChecked(True)

        # 3. fecha UI de adição
        self.palette_dock.hide()
        self.actions["open_palette"].setChecked(False)

        self.view.cleanup_temp_connection()
        self.view.cleanup_node_preview()

        self.view.unsetCursor()

    def new_scene(self):
        self.set_mode(EditorMode.SELECT)
        self.scene = GraphicsScene()

        self.delete_manager.scene = self.scene

        self.view.setScene(self.scene)
        self.simulation = SimulationSession(self.scene)
        self.file_session = SceneFileSession(self.scene, self, self.state)
        self._wire_state_callbacks()
        self.state.undo_stack.clear()
        self.setWindowTitle("Simulador – Editor Gráfico")
        self.update_scene_rect()


    def set_mode(self, mode: EditorMode, node_desc=None):
        self.state.mode = mode
        self.view.cleanup_node_preview()
        self.view.cleanup_temp_connection()
        self.state.pending_node = node_desc

        if mode != EditorMode.ADD:
            self.node_palette.clear_selection()

        is_select_mode = (mode == EditorMode.SELECT)

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

        if mode == EditorMode.SIMULATE:
            self.start_simulation()
            if not self.simulation.active:
                # start falhou (props faltando) — volta para SELECT sem recursar
                self.state.mode = EditorMode.SELECT
                self._update_mode_actions(EditorMode.SELECT)
                self.update_simulation_actions()
                return
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

    def on_change_font_size(self):
        if settings.prompt_and_apply_font_size(self):
            self.node_palette.set_size_tier(self.node_palette.current_tier, persist=False)
            for item in self.scene.items():
                if isinstance(item, LabelItem):
                    item.refresh_default_font_size()

    def add_node_at(self, x, y):
        if not self.state.pending_node:
            return

        # Captura snapshot ANTES de adicionar o nó
        from editor.undo import UndoStack
        before = UndoStack.snapshot(self.scene)

        item = self.state.pending_node.cls(
            domain=self.state.pending_node.domain,
            sensor_registry=self.scene.sensor_registry)
        item.editor = self.state

        w = item.boundingRect().width()
        h = item.boundingRect().height()

        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        item.setPos(x - w / 2, y - h / 2)

        self.scene.addItem(item)
        self.update_scene_rect()

        # Empilha o command de undo APÓS o nó ser adicionado
        self.state.undo_stack.push_snapshot(self.scene, self.state, before, "Adicionar nó")

        self.set_mode(EditorMode.SELECT)

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
        if self.state.active_context_menu:
            self.state.active_context_menu.close()
            self.state.active_context_menu = None

        # domain/editor concern
        deleted = self.delete_manager.delete_selection(editor_state=self.state)
        if deleted:
            self.update_scene_rect()

    def toggle_node_palette(self, checked):
        self.palette_dock.setVisible(checked)

    def start_simulation(self):
        error = self.simulation.start()
        if error:
            QMessageBox.warning(self, "Propriedades incompletas", error)
            return
        self.simulation.controller.state_changed.connect(self.update_simulation_actions)

    def stop_simulation(self):
        self.simulation.stop()

    def save_scene(self):
        self.file_session.save()

    def save_scene_as(self):
        self.file_session.save_as()

    def open_scene(self):
        self.set_mode(EditorMode.SELECT)
        self.file_session.open()

    def toggle_play(self):
        if self.state.mode != EditorMode.SIMULATE:
            self.set_mode(EditorMode.SIMULATE)

        self.simulation.toggle_play()
        self.update_simulation_actions()

    def on_step_back(self):
        if self.simulation.controller.step_backward():
            self.update_simulation_actions()


    def on_step_forward(self):
        if self.simulation.controller.step_forward():
            self.update_simulation_actions()

    def on_dt_clicked(self):
        from PyQt6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getDouble(
            self, "Step size", "dt (s):",
            self.simulation.dt,  # lê da session
            0.001, 1.0, 3
        )
        if ok:
            self.simulation.dt = value  # salva na session
            if self.simulation.controller:
                self.simulation.controller.set_dt(value)
            self.actions["dt"].setText(f"dt: {value:.3f}s")

    def on_cycle_speed(self):
        self.simulation.speed_index = (self.simulation.speed_index + 1) % len(SPEED_STEPS)
        multiplier = SPEED_STEPS[self.simulation.speed_index]
        self.simulation.timer_interval = 1000 // multiplier  # salva na session
        if self.simulation.controller:
            self.simulation.controller.set_timer_interval(self.simulation.timer_interval)
        self.actions["speed"].setText(f"{multiplier}x")

    def update_simulation_actions(self):
        run       = self.actions["run"]
        step_back = self.actions["step_back"]
        step_fwd  = self.actions["step_forward"]

        in_simulation = (
            self.state.mode == EditorMode.SIMULATE
            and self.simulation
            and self.simulation.active
        )

        if not in_simulation:
            run.setEnabled(False)
            run.setText("Run")
            step_back.setEnabled(False)
            step_fwd.setEnabled(False)
            return

        ctrl = self.simulation.controller

        run.setEnabled(True)
        run.setText("Pause" if ctrl.playing else "Run")

        steps_enabled = not ctrl.playing
        step_back.setEnabled(steps_enabled and ctrl.can_step_back())
        step_fwd.setEnabled(steps_enabled)
    def _update_mode_actions(self, active_mode):
        for action in self.mode_group.actions():
            action.setChecked(action.data() == active_mode)

    def set_light_theme(self, enabled: bool):
        self.use_light_theme = enabled
        self.state.is_light_theme = enabled

        # 🔹 tema da aplicação inteira (toolbar, menus, docks, diálogos)
        theme.apply_theme(QApplication.instance(), enabled)

        # 🔹 muda fundo
        if not enabled:
            self.view.setBackgroundBrush(QBrush(QColor(30, 30, 30)))  # cinza escuro
        else:
            self.view.setBackgroundBrush(QBrush(QColor(255, 255, 255)))  # branco

        # 🔹 notifica nodes
        self.state.theme_changed.emit(enabled)

        # 🔹 atualiza texto botão
        self.actions["toggle_theme"].setText(
            "Light Theme" if enabled else "Dark Theme"
        )