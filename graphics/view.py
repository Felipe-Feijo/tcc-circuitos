# graphics/view.py
from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPen

from graphics.items.base.connections.connection_item import ConnectionItem
from editor.mode import EditorMode
from graphics.items.base.nodes.node_item import NodeItem

class GraphicsView(QGraphicsView):

    ZOOM_IN_FACTOR = 1.25
    ZOOM_OUT_FACTOR = 0.8

    def __init__(self, editor_state, *args):
        super().__init__(*args)
        self.editor = editor_state  # EditorState

        self._panning = False
        self._pan_start = None

        self._temp_connection = None

        self._preview_node = None

        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

    MIN_ZOOM = 0.1

    def zoom_in(self):
        self.scale(self.ZOOM_IN_FACTOR, self.ZOOM_IN_FACTOR)
        if self.editor:
            self.editor.update_scene_rect()

    def zoom_out(self):
        if self.transform().m11() * self.ZOOM_OUT_FACTOR < self.MIN_ZOOM:
            return
        self.scale(self.ZOOM_OUT_FACTOR, self.ZOOM_OUT_FACTOR)
        if self.editor:
            self.editor.update_scene_rect()

    def zoom_to_contents(self):
        scene = self.scene()
        if not scene:
            return

        items_rect = scene.itemsBoundingRect()
        if items_rect.isNull():
            return

        self.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)

        if self.editor:
            self.editor.update_scene_rect()

    def wheelEvent(self, event):
        # Define o ponto de ancoragem como o mouse
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        
        # Restaura a ancoragem original
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.editor.mode == EditorMode.ADD and self.editor.pending_node:
            scene_pos = self.mapToScene(event.pos())
            self.cleanup_node_preview()
            self.editor.add_node_at(scene_pos.x(), scene_pos.y())
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            # If the cursor is over a waypoint on a connection, let the
            # event reach the item instead of starting a pan.
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
        
        if (event.button() == Qt.MouseButton.LeftButton and self.editor.mode == EditorMode.CONNECT):
            if self.editor._connecting:
                target_anchor = self.editor.hover_anchor
                source_anchor = self.editor._conn_source_anchor
                source_item = source_anchor.node if source_anchor else None

                self.cleanup_temp_connection()

                if target_anchor and source_item and target_anchor.node is not source_item:
                    self.create_connection(source_item, source_anchor, target_anchor.node, target_anchor)
            else:
                self.handle_connect_press(event)
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
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
            else:
                self.unsetCursor()
            if self.editor._connecting:
                if self._temp_connection and self._temp_connection.scene():
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
                scene_pos.y() - h / 2
            )

            event.accept()
            return


        super().mouseMoveEvent(event)


    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            if self.editor:
                self.editor.update_scene_rect()
            return
    

        super().mouseReleaseEvent(event)

    def handle_connect_press(self, event):
        anchor = self.editor.hover_anchor
        if not anchor:
            return

        self.editor._connecting = True
        self.editor._conn_source_anchor = anchor

        self.start_temp_connection(anchor.node, anchor)


    def create_connection(self, source_item, source_anchor, target_item, target_anchor):
        source = source_item

        # 🔒 PROTEÇÃO DE DUPLICATA
        for conn in source.connections:
            if (conn.source is source
                and conn.target is target_item
                and conn.source_anchor == source_anchor
                and conn.target_anchor == target_anchor):

                print("⚠️ Duplicate connection ignored")
                return

        conn = ConnectionItem(
            source,
            source_anchor,
            target_item,
            target_anchor
        )
        conn.editor = self.editor

        self.scene().addItem(conn)

        source.connections.append(conn)
        target_item.connections.append(conn)

    def start_temp_connection(self, source_item, source_anchor):
        self._temp_connection = ConnectionItem(source_item, source_anchor)

        pen = QPen(Qt.GlobalColor.darkGray, 2, Qt.PenStyle.DashLine)
        self._temp_connection.pen = pen
        self._temp_connection.setZValue(-1)

        self.scene().addItem(self._temp_connection)

        source_anchor.setBrush(Qt.GlobalColor.gray)
        source_anchor.update()


    def cleanup_temp_connection(self):
        if self._temp_connection:
            self.scene().removeItem(self._temp_connection)
            self._temp_connection = None

        if self.editor._conn_source_anchor:
            self.editor._conn_source_anchor.setBrush(Qt.GlobalColor.transparent)
            self.editor._conn_source_anchor.update()

        self.editor._connecting = False
        self.editor._conn_source_anchor = None


    def start_node_preview(self):
        if self._preview_node:
            return

        if not self.editor.pending_node:
            return

        desc = self.editor.pending_node
        item = desc.cls(domain=desc.domain)
        item.apply_preview_constraints()

        self._preview_node = item
        self.scene().addItem(item)

    def cleanup_node_preview(self):
        if self._preview_node:
            self.scene().removeItem(self._preview_node)
            self._preview_node = None