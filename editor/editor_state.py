from PyQt6.QtCore import QObject, pyqtSignal


class EditorState(QObject):
    """
    Holds the mutable interaction state of the diagram editor.

    Owned by MainWindow and passed to GraphicsView, DiagramItemBase,
    and AnchorItem so they don't need a direct reference to the window.

    Attributes:
        mode          -- current editor mode (EditorMode enum)
        pending_node  -- NodeDescriptor selected in the palette (only in ADD mode)
        hover_anchor  -- AnchorItem currently under the cursor (only in CONNECT mode)
        active_context_menu -- QMenu currently open, used to close it on delete

    Signals:
        add_node_requested(x, y)         -- user clicked to place a node
        scene_rect_update_requested()    -- scene rect should recalculate
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

        # Connection drag state — owned here, read by GraphicsView and AnchorItem
        self._connecting: bool = False
        self._conn_source_anchor = None

        # dict of QActions for context menus — set by MainWindow after construction
        self.actions: dict = {}

    # Convenience wrappers so call sites read naturally
    def add_node_at(self, x: float, y: float) -> None:
        self.add_node_requested.emit(x, y)

    def update_scene_rect(self) -> None:
        self.scene_rect_update_requested.emit()
