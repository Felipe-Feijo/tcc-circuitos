"""Mutable interaction state of the diagram editor."""

from PyQt6.QtCore import QObject, pyqtSignal

from editor.undo import UndoStack


class EditorState(QObject):
    """Centralizes the editor's interaction state.

    Owned by MainWindow and passed to GraphicsView, DiagramItemBase
    and AnchorItem, eliminating direct references to the main window.

    Attributes:
        mode: Current editor mode (EditorMode enum).
        pending_node: NodeDescriptor selected in the palette (ADD mode only).
        hover_anchor: AnchorItem under the cursor (CONNECT mode only).
        active_context_menu: Currently open QMenu, closed on delete.
        actions: Dict of QActions filled in by MainWindow after construction.
        undo_stack: Undo/redo stack shared across the whole editor.
        is_light_theme: Current theme, kept in sync with MainWindow.set_light_theme.
            Items created after a toggle (without listening to the theme_changed
            signal) read this value to be born with the right color already.

    Signals:
        add_node_requested(x, y): User clicked to place a node.
        scene_rect_update_requested: The scene rect must be recomputed.
        theme_changed(is_light): The application theme changed.
    """

    add_node_requested = pyqtSignal(float, float)
    scene_rect_update_requested = pyqtSignal()
    theme_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        self.mode = None
        self.pending_node = None
        self.hover_anchor = None
        self.active_context_menu = None

        # Connection-drag state -- read by GraphicsView and AnchorItem
        self._connecting: bool = False
        self._conn_source_anchor = None

        self.actions: dict = {}
        self.is_light_theme: bool = False

        # Undo/redo stack -- used by DeleteManager, ClipboardManager,
        # GraphicsView and MainWindow
        self.undo_stack = UndoStack()
        self.undo_stack.setUndoLimit(50)

    def add_node_at(self, x: float, y: float) -> None:
        """Emits the signal to place a node at the scene coordinates.

        Args:
            x: Horizontal coordinate in the scene.
            y: Vertical coordinate in the scene.
        """
        self.add_node_requested.emit(x, y)

    def update_scene_rect(self) -> None:
        """Requests recomputation of the scene rect."""
        self.scene_rect_update_requested.emit()
