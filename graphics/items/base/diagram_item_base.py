"""Base class for every graphics item in the diagram."""

from PyQt6.QtWidgets import QGraphicsItem, QMenu, QGraphicsObject
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtCore import Qt

from editor.mode import EditorMode


class DiagramItemBase(QGraphicsObject):
    """Common base for NodeItem and ConnectionItem.

    Provides:
    - Qt selection enabled by default.
    - Scene rect update on mouse release.
    - Context menu in SELECT and SIMULATE modes, extensible by
      subclasses via extend_context_menu(). In SIMULATE, "Delete" is
      left out (project editing stays disabled) -- only entries each
      subclass has decided to expose during simulation (checking
      self.simulation_mode) appear; see NodeItem.extend_context_menu().
    - Selection-highlight rendering via paint_selection_feedback().

    Attributes:
        editor: EditorState injected after the item is added to the scene.
        draw_selection: If False, suppresses the blue selection highlight.
    """

    def __init__(self):
        super().__init__()
        self.editor = None
        self.draw_selection = True
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def mouseReleaseEvent(self, event):
        """Requests a scene rect update on mouse release."""
        super().mouseReleaseEvent(event)
        if self.editor:
            self.editor.update_scene_rect()

    def contextMenuEvent(self, event):
        """Shows the context menu in SELECT and SIMULATE modes; ignored otherwise.

        In SIMULATE, "Delete" isn't offered (deleting a node/connection
        mid-simulation would corrupt the running domain graph); the rest
        of the menu's content is decided by extend_context_menu(), which
        each subclass already restricts to simulation-aware entries when
        self.simulation_mode is True.
        """
        if not self.editor:
            return
        if not self._context_menu_allowed():
            event.ignore()
            return

        scene = self.scene()
        if not self.isSelected():
            scene.clearSelection()
            self.setSelected(True)

        menu = QMenu()
        self.editor.active_context_menu = menu
        if self.editor.mode == EditorMode.SELECT:
            menu.addAction(self.editor.actions["delete"])
        self.extend_context_menu(menu)

        if menu.isEmpty():
            # In SIMULATE, most items have no simulation-aware entry at
            # all (e.g. only Valve_4_2_Ways defines build_defect_dialog so
            # far) -- without this, right-click would open an empty gray
            # popup on almost every node during simulation.
            self.editor.active_context_menu = None
            event.ignore()
            return

        menu.exec(event.screenPos())
        self.editor.active_context_menu = None
        event.accept()

    def _context_menu_allowed(self) -> bool:
        """True if the context menu should open in the editor's current mode.

        SELECT: normal project editing. SIMULATE: simulation running --
        the menu still opens, but with restricted content (no "Delete";
        the rest depends on each subclass checking self.simulation_mode
        in extend_context_menu()). ADD/CONNECT: blocked, as before.
        """
        return self.editor.mode in (EditorMode.SELECT, EditorMode.SIMULATE)

    def extend_context_menu(self, menu: QMenu) -> None:
        """Lets subclasses add entries to the context menu.

        Called by contextMenuEvent before showing the menu. No-op by default.
        """

    def paint_selection_feedback(self, painter) -> None:
        """Draws the selection highlight (blue) and/or active-defect highlight (red)."""
        if self.draw_selection and self.isSelected():
            pen = QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.shape())

        if getattr(self, "_defect_indicator", False):
            pen = QPen(QColor("#e74c3c"), 3, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.shape())

    def update_from_domain(self, domain_node) -> None:
        """Updates visual state from the domain node. No-op by default."""
