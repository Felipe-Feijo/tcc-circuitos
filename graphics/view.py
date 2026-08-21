"""Diagram editor viewport: zoom, pan and mouse interaction."""

from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPen

from graphics.items.base.connections.connection_item import ConnectionItem
from editor.mode import EditorMode
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem


class GraphicsView(QGraphicsView):
    """QGraphicsView subclass with zoom, pan and editor-mode support.

    Delegates mode decisions to the EditorState injected in the
    constructor, keeping the view free of business logic.

    Modes handled:
    - SELECT: default Qt behavior (rubber-band, movement).
    - ADD: shows a preview of the node under the cursor and places it on click.
    - CONNECT: starts/completes a connection between anchors on click.
    - SIMULATE: no editing interaction.

    Attrs:
        ZOOM_IN_FACTOR: Magnification factor per zoom step.
        ZOOM_OUT_FACTOR: Reduction factor per zoom step.
        MIN_ZOOM: Minimum zoom level (avoids viewport collapse).
    """

    ZOOM_IN_FACTOR = 1.25
    ZOOM_OUT_FACTOR = 0.8
    MIN_ZOOM = 0.1

    def __init__(self, editor_state, *args):
        super().__init__(*args)
        self.editor = editor_state

        self._panning = False
        self._pan_start = None
        self._temp_connection = None
        self._preview_node = None

        # Snapshot captured at the start of a node drag, for move undo
        self._move_before_snapshot = None

        # Snapshot captured if a CONNECT gesture involved a connection split
        # (line->anchor or anchor->line) -- used to undo the split if the
        # gesture is canceled, or to push a single combined undo if the
        # connection is created.
        self._connect_before_snapshot = None

        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

    # Zoom

    def zoom_in(self) -> None:
        """Enlarges the viewport by the ZOOM_IN_FACTOR."""
        self.scale(self.ZOOM_IN_FACTOR, self.ZOOM_IN_FACTOR)
        if self.editor:
            self.editor.update_scene_rect()

    def zoom_out(self) -> None:
        """Shrinks the viewport by ZOOM_OUT_FACTOR, respecting MIN_ZOOM."""
        if self.transform().m11() * self.ZOOM_OUT_FACTOR < self.MIN_ZOOM:
            return
        self.scale(self.ZOOM_OUT_FACTOR, self.ZOOM_OUT_FACTOR)
        if self.editor:
            self.editor.update_scene_rect()

    def zoom_to_contents(self) -> None:
        """Adjusts the zoom to frame every item in the scene."""
        scene = self.scene()
        if not scene:
            return
        items_rect = scene.itemsBoundingRect()
        if items_rect.isNull():
            return
        self.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self.editor:
            self.editor.update_scene_rect()

    # Mouse events

    def wheelEvent(self, event) -> None:
        """Applies zoom via the mouse wheel, anchored under the cursor."""
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def mousePressEvent(self, event) -> None:
        """Handles clicks according to the editor's current mode."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.editor.mode == EditorMode.ADD
            and self.editor.pending_node
        ):
            scene_pos = self.mapToScene(event.pos())
            self.cleanup_node_preview()
            self.editor.add_node_at(scene_pos.x(), scene_pos.y())
            event.accept()
            return

        if event.button() == Qt.MouseButton.MiddleButton:
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            # If the cursor is over a connection waypoint, forward the event
            # to the item instead of starting a pan.
            scene_pos = self.mapToScene(event.pos())
            for item in self.scene().items(scene_pos):
                if isinstance(item, ConnectionItem):
                    if item._wp_index_at(scene_pos) is not None:
                        super().mousePressEvent(event)
                        return
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.editor.mode == EditorMode.CONNECT
        ):
            if self.editor._connecting:
                self._complete_connect_press(event)
            else:
                self.handle_connect_press(event)
            return

        super().mousePressEvent(event)

        # Captures a snapshot BEFORE the node drag, for move undo.
        # Only captures if some NodeItem ended up selected after the click.
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.editor.mode == EditorMode.SELECT
        ):
            scene_pos = self.mapToScene(event.pos())
            hit = self.scene().items(scene_pos)
            if any(isinstance(i, NodeItem) for i in hit):
                from editor.undo import UndoStack
                self._move_before_snapshot = UndoStack.snapshot(self.scene())

    def mouseMoveEvent(self, event) -> None:
        """Updates pan, the temp connection, or the node preview based on the mode."""
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return

        if self.editor.mode == EditorMode.CONNECT:
            if self.editor.hover_anchor:
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif self._connection_at(self.mapToScene(event.pos()), exclude={self._temp_connection}):
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.unsetCursor()
            if self.editor._connecting and self._temp_connection and self._temp_connection.scene():
                scene_pos = self.mapToScene(event.pos())
                self._temp_connection.update_temp_endpoint(scene_pos)

        if self.editor.mode == EditorMode.ADD and self.editor.pending_node:
            scene_pos = self.mapToScene(event.pos())
            if not self._preview_node:
                self.start_node_preview()
            w = self._preview_node.boundingRect().width()
            h = self._preview_node.boundingRect().height()
            self._preview_node.setPos(
                scene_pos.x() - w / 2,
                scene_pos.y() - h / 2,
            )
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Ends the pan when the right button is released."""
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            if self.editor:
                self.editor.update_scene_rect()
            return

        super().mouseReleaseEvent(event)

        # If there was a drag-start snapshot, checks whether any node
        # actually moved and pushes the undo command only in that case.
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._move_before_snapshot is not None
        ):
            from persistence.serializer import serialize_scene
            after = serialize_scene(self.scene())
            before_positions = {
                n["id"]: n["position"]
                for n in self._move_before_snapshot.get("nodes", [])
            }
            after_positions = {
                n["id"]: n["position"]
                for n in after.get("nodes", [])
            }
            if before_positions != after_positions:
                self.editor.undo_stack.push_snapshot(
                    self.scene(),
                    self.editor,
                    self._move_before_snapshot,
                    "Mover nó",
                )
            self._move_before_snapshot = None

    # Connection creation

    def handle_connect_press(self, event) -> None:
        """Starts a new connection from the anchor under the cursor -- or,
        if there's no anchor under the cursor, from a point on an
        existing ConnectionItem (creates a JunctionNodeItem there and
        starts from it, as if it were a regular anchor)."""
        anchor = self.editor.hover_anchor
        if not anchor:
            scene_pos = self.mapToScene(event.pos())
            conn = self._connection_at(scene_pos)
            if conn is None:
                return
            from editor.undo import UndoStack
            self._connect_before_snapshot = UndoStack.snapshot(self.scene())
            anchor = self.split_connection_at(conn, scene_pos)
            if anchor is None:
                self._connect_before_snapshot = None
                return
        self.editor._connecting = True
        self.editor._conn_source_anchor = anchor
        self.start_temp_connection(anchor.node, anchor)

    def _complete_connect_press(self, event) -> None:
        """CONNECT mode's second click: completes the connection at an
        anchor, at a point on an existing line (split + junction), or
        cancels (click on empty space). If a split happened during this
        gesture (at the start or now) and the connection ends up not
        being created, undoes the split via a snapshot rollback -- no
        orphan junction should be left over from a canceled gesture.

        Pops `_connect_before_snapshot` into a local variable and clears
        the instance attribute BEFORE calling cleanup_temp_connection():
        this guarantees cleanup_temp_connection() (which now also
        covers Escape/mode switch -- see its docstring) never sees a
        snapshot belonging to a gesture that THIS method is about to
        complete successfully. Only the other callers of
        cleanup_temp_connection (which never do this pop beforehand)
        leave the snapshot there for cleanup_temp_connection to roll
        back."""
        target_anchor = self.editor.hover_anchor
        source_anchor = self.editor._conn_source_anchor
        source_item = source_anchor.node if source_anchor else None

        if target_anchor is None and source_anchor is not None:
            scene_pos = self.mapToScene(event.pos())
            conn = self._connection_at(scene_pos, exclude={self._temp_connection})
            if conn is not None and conn.domain == source_anchor.domain:
                if self._connect_before_snapshot is None:
                    from editor.undo import UndoStack
                    self._connect_before_snapshot = UndoStack.snapshot(self.scene())
                target_anchor = self.split_connection_at(conn, scene_pos)

        before_snapshot = self._connect_before_snapshot
        self._connect_before_snapshot = None
        self.cleanup_temp_connection()

        created = None
        if target_anchor and source_item and target_anchor.node is not source_item:
            created = self.create_connection(
                source_item, source_anchor,
                target_anchor.node, target_anchor,
                record_undo=before_snapshot is None,
            )

        if before_snapshot is not None:
            if created is not None:
                self.editor.undo_stack.push_snapshot(
                    self.scene(), self.editor, before_snapshot, "Criar conexão",
                )
            else:
                from editor.undo import _restore_snapshot
                _restore_snapshot(before_snapshot, self.scene(), self.editor)

    def _connection_at(self, scene_pos, exclude=None):
        """First ConnectionItem whose compute_split_point accepts
        scene_pos (i.e. the cursor is close enough to one of its
        segments), ignoring the items in `exclude` (typically the
        temporary preview connection)."""
        exclude = exclude or set()
        for item in self.scene().items(scene_pos):
            if (isinstance(item, ConnectionItem) and item not in exclude
                    and item.compute_split_point(scene_pos) is not None):
                return item
        return None

    def split_connection_at(self, conn: ConnectionItem, scene_pos):
        """Splits `conn` into two, linking both pieces to a new
        JunctionNodeItem positioned at scene_pos (projected onto `conn`'s
        route). Returns the junction's "J" AnchorItem, or None if
        scene_pos isn't close enough to any of `conn`'s segments."""
        split = conn.compute_split_point(scene_pos)
        if split is None:
            return None
        point, wp_before, wp_after = split

        junction = JunctionNodeItem(domain=conn.domain)
        junction.editor = self.editor
        junction.setPos(point)
        self.scene().addItem(junction)
        j_anchor = junction.anchors["J"]

        source_item, source_anchor = conn.source, conn.source_anchor
        target_item, target_anchor = conn.target, conn.target_anchor

        conn_a = ConnectionItem(source_item, source_anchor, junction, j_anchor)
        conn_a.waypoints = list(wp_before)
        conn_a._waypoints_initialized = True
        conn_a.editor = self.editor

        conn_b = ConnectionItem(junction, j_anchor, target_item, target_anchor)
        conn_b.waypoints = list(wp_after)
        conn_b._waypoints_initialized = True
        conn_b.editor = self.editor

        self.scene().addItem(conn_a)
        self.scene().addItem(conn_b)
        source_item.connections.append(conn_a)
        junction.connections.append(conn_a)
        junction.connections.append(conn_b)
        target_item.connections.append(conn_b)

        # wp_before/wp_after were captured under the ORIGINAL connection's
        # (conn) margins -- the junction's "J" anchor accepts all 4
        # directions, so conn_a/conn_b's "ideal" direction can differ
        # from conn's even with nothing having moved. Without this, the
        # segment near the junction can come out diagonal right here.
        conn_a.reanchor_waypoints()
        conn_b.reanchor_waypoints()

        # The original connection's prepare_delete()+removeItem() are
        # deferred as one atomic unit via QTimer.singleShot(0, ...) --
        # same pattern as editor/delete_manager.py
        # (DeleteManager.do_delete) and NodeItem.remove_anchor.
        # split_connection_at runs from inside mousePressEvent; doing
        # this synchronously already caused a "Windows fatal exception:
        # access violation" in a subsequent real mouseMoveEvent by
        # leaving the QGraphicsScene's spatial index (BSP) inconsistent
        # (see
        # tests/test_node_item_remove_anchor_defers_scene_removal.py).
        # Creating the junction/child connections and the
        # refresh_junction_dot() calls below stay synchronous -- they're
        # not the risky operation.
        #
        # Rebuilding the spatial index below (invalidate + toggling
        # itemIndexMethod) is a REQUIRED part of this same mitigation,
        # not an extra -- without it, the BSP index stays consistent
        # enough to not crash immediately, but still holds stale entries
        # that corrupt a later spatial query (scene().items(pos), used
        # by _connection_at on every mouseMoveEvent in CONNECT mode) on
        # a subsequent event cycle -- reproduced for real: a "Windows
        # fatal exception: access violation" in
        # GraphicsView._connection_at called from mouseMoveEvent,
        # minutes after a split.
        def _finish_old_connection_removal():
            conn.prepare_delete()
            scene = self.scene()
            if conn.scene():
                scene.removeItem(conn)
            ConnectionItem._rebuild_scene_index(scene)
        QTimer.singleShot(0, _finish_old_connection_removal)

        source_anchor.refresh_junction_dot()
        target_anchor.refresh_junction_dot()
        j_anchor.refresh_junction_dot()

        return j_anchor

    def create_connection(self, source_item, source_anchor, target_item, target_anchor,
                           *, record_undo: bool = True):
        """Creates a ConnectionItem between two anchors, ignoring
        duplicates.

        Args:
            source_item: source NodeItem.
            source_anchor: exit AnchorItem on the source node.
            target_item: target NodeItem.
            target_anchor: entry AnchorItem on the target node.
            record_undo: If True (default), captures and pushes the undo
                snapshot right here. Callers that already do their own
                snapshot capture around a composite operation (e.g.
                split + connect from a click on a junction) pass False
                and handle undo themselves.

        Returns:
            The created ConnectionItem, or None if an identical
            connection (source/target/anchors) already existed and
            nothing was done.
        """
        for conn in source_item.connections:
            if (
                conn.source is source_item
                and conn.target is target_item
                and conn.source_anchor == source_anchor
                and conn.target_anchor == target_anchor
            ):
                return None

        before = None
        if record_undo:
            from editor.undo import UndoStack
            before = UndoStack.snapshot(self.scene())

        conn = ConnectionItem(source_item, source_anchor, target_item, target_anchor)
        conn.editor = self.editor
        self.scene().addItem(conn)
        source_item.connections.append(conn)
        target_item.connections.append(conn)
        source_anchor.refresh_junction_dot()
        target_anchor.refresh_junction_dot()

        if record_undo:
            self.editor.undo_stack.push_snapshot(
                self.scene(), self.editor, before, "Criar conexão",
            )
        return conn

    def start_temp_connection(self, source_item, source_anchor) -> None:
        """Creates the temporary (dashed) preview ConnectionItem.

        Args:
            source_item: source NodeItem of the connection in progress.
            source_anchor: the selected exit AnchorItem.
        """
        self._temp_connection = ConnectionItem(source_item, source_anchor)
        pen = QPen(Qt.GlobalColor.darkGray, 2, Qt.PenStyle.DashLine)
        self._temp_connection.pen = pen
        self._temp_connection.setZValue(-1)
        self.scene().addItem(self._temp_connection)
        source_anchor.setBrush(Qt.GlobalColor.gray)
        source_anchor.update()

    def cleanup_temp_connection(self) -> None:
        """Removes the temporary preview connection and restores the
        anchor's state.

        Called at the end of ANY CONNECT gesture -- success (via
        _complete_connect_press), cancellation by clicking empty space
        (same), Escape (MainWindow.cancel_current_mode), or a mode
        switch from the toolbar (MainWindow.set_mode). That also makes
        this the only correct place to handle a pending
        `_connect_before_snapshot`: if the gesture involved a connection
        split (line->anchor or anchor->line) and a snapshot is still
        here when this method is called, it means the gesture is being
        aborted through one of these external paths (not through
        _complete_connect_press, which already clears the attribute
        BEFORE calling this method when the gesture is about to
        complete successfully -- see its docstring) -- undoes the split
        via rollback, otherwise it becomes a scene mutation not recorded
        in undo, "leaking" into the next CONNECT gesture and making the
        next cancellation revert to this stale snapshot."""
        if self._temp_connection:
            self.scene().removeItem(self._temp_connection)
            self._temp_connection = None
        if self.editor._conn_source_anchor:
            self.editor._conn_source_anchor.refresh_junction_dot()
        self.editor._connecting = False
        self.editor._conn_source_anchor = None

        if self._connect_before_snapshot is not None:
            from editor.undo import _restore_snapshot
            _restore_snapshot(self._connect_before_snapshot, self.scene(), self.editor)
            self._connect_before_snapshot = None

    # Node preview

    def start_node_preview(self) -> None:
        """Instantiates the pending node as a semi-transparent preview in the scene."""
        if self._preview_node or not self.editor.pending_node:
            return
        desc = self.editor.pending_node
        item = desc.cls(domain=desc.domain)
        item.editor = self.editor
        item.apply_preview_constraints()
        self._preview_node = item
        self.scene().addItem(item)

    def cleanup_node_preview(self) -> None:
        """Removes the preview node from the scene."""
        if self._preview_node:
            self.scene().removeItem(self._preview_node)
            self._preview_node = None
