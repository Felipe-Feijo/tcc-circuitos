from typing import Callable


class EditorState:
    """
    Holds the mutable interaction state of the diagram editor.

    Owned by MainWindow and passed to GraphicsView, DiagramItemBase,
    and AnchorItem so they don't need a direct reference to the window.

    Attributes:
        mode          -- current editor mode: None | "connect" | "add" | "simulate"
        pending_node  -- NodeDescriptor selected in the palette (only in "add" mode)
        hover_anchor  -- AnchorItem currently under the cursor (only in "connect" mode)
        active_context_menu -- QMenu currently open, used to close it on delete

    Callbacks (set by MainWindow after construction):
        on_add_node(x, y)  -- place the pending node at scene coordinates
        on_scene_rect_update() -- recalculate and update the scene rect
        actions            -- dict of QActions, for context menus
    """

    def __init__(self):
        self.mode = None
        self.pending_node = None
        self.hover_anchor = None
        self.active_context_menu = None

        # Connection drag state (mirrors GraphicsView._connecting/_conn_source_anchor)
        # Updated by GraphicsView so AnchorItem doesn't need a view reference
        self._connecting: bool = False
        self._conn_source_anchor = None

        # Set by MainWindow after construction
        self.on_add_node: Callable[[float, float], None] = lambda x, y: None
        self.on_scene_rect_update: Callable[[], None] = lambda: None
        self.actions: dict = {}

    # Convenience wrappers so call sites read naturally
    def add_node_at(self, x: float, y: float) -> None:
        self.on_add_node(x, y)

    def update_scene_rect(self) -> None:
        self.on_scene_rect_update()
