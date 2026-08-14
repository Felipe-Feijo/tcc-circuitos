"""Viewport do editor de diagramas: zoom, pan e interação de mouse."""

from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPen

from graphics.items.base.connections.connection_item import ConnectionItem
from editor.mode import EditorMode
from graphics.items.base.nodes.node_item import NodeItem


class GraphicsView(QGraphicsView):
    """Subclasse de QGraphicsView com suporte a zoom, pan e modos do editor.

    Delega decisões de modo ao EditorState injetado no construtor, mantendo
    a view livre de lógica de negócio.

    Modos tratados:
    - SELECT: comportamento padrão do Qt (rubber-band, movimentação).
    - ADD: exibe preview do nó sob o cursor e posiciona ao clicar.
    - CONNECT: inicia/completa conexão entre âncoras ao clicar.
    - SIMULATE: nenhuma interação de edição.

    Attrs:
        ZOOM_IN_FACTOR: Fator de ampliação por passo de zoom.
        ZOOM_OUT_FACTOR: Fator de redução por passo de zoom.
        MIN_ZOOM: Nível mínimo de zoom (evita colapso da viewport).
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

        # Snapshot capturado no início de um arrasto de nó para undo de move
        self._move_before_snapshot = None

        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

    # Zoom

    def zoom_in(self) -> None:
        """Amplia a viewport pelo fator ZOOM_IN_FACTOR."""
        self.scale(self.ZOOM_IN_FACTOR, self.ZOOM_IN_FACTOR)
        if self.editor:
            self.editor.update_scene_rect()

    def zoom_out(self) -> None:
        """Reduz a viewport pelo fator ZOOM_OUT_FACTOR, respeitando MIN_ZOOM."""
        if self.transform().m11() * self.ZOOM_OUT_FACTOR < self.MIN_ZOOM:
            return
        self.scale(self.ZOOM_OUT_FACTOR, self.ZOOM_OUT_FACTOR)
        if self.editor:
            self.editor.update_scene_rect()

    def zoom_to_contents(self) -> None:
        """Ajusta o zoom para enquadrar todos os itens da cena."""
        scene = self.scene()
        if not scene:
            return
        items_rect = scene.itemsBoundingRect()
        if items_rect.isNull():
            return
        self.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self.editor:
            self.editor.update_scene_rect()

    # Eventos de mouse

    def wheelEvent(self, event) -> None:
        """Aplica zoom com a roda do mouse, ancorado sob o cursor."""
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def mousePressEvent(self, event) -> None:
        """Trata cliques de acordo com o modo atual do editor."""
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
            # Se o cursor estiver sobre um waypoint de conexão, repassa o evento
            # ao item em vez de iniciar pan.
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
                target_anchor = self.editor.hover_anchor
                source_anchor = self.editor._conn_source_anchor
                source_item = source_anchor.node if source_anchor else None

                self.cleanup_temp_connection()

                if target_anchor and source_item and target_anchor.node is not source_item:
                    self.create_connection(
                        source_item, source_anchor,
                        target_anchor.node, target_anchor,
                    )
            else:
                self.handle_connect_press(event)
            return

        super().mousePressEvent(event)

        # Captura snapshot ANTES do arrasto de nó para undo de move.
        # Só captura se algum NodeItem ficou selecionado após o clique.
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
        """Atualiza pan, conexão temporária ou preview de nó conforme o modo."""
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
        """Encerra o pan ao soltar o botão direito."""
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            if self.editor:
                self.editor.update_scene_rect()
            return

        super().mouseReleaseEvent(event)

        # Se havia um snapshot de início de arrasto, verifica se algum nó
        # se moveu e empilha o command de undo apenas nesse caso.
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

    # Criação de conexões

    def handle_connect_press(self, event) -> None:
        """Inicia uma nova conexão a partir do âncora sob o cursor.

        Só age se houver um hover_anchor definido no EditorState.
        """
        anchor = self.editor.hover_anchor
        if not anchor:
            return
        self.editor._connecting = True
        self.editor._conn_source_anchor = anchor
        self.start_temp_connection(anchor.node, anchor)

    def create_connection(self, source_item, source_anchor, target_item, target_anchor) -> None:
        """Cria uma ConnectionItem entre dois âncoras, ignorando duplicatas.

        Args:
            source_item: NodeItem de origem.
            source_anchor: AnchorItem de saída no nó de origem.
            target_item: NodeItem de destino.
            target_anchor: AnchorItem de entrada no nó de destino.
        """
        # Proteção contra conexão duplicada entre os mesmos âncoras
        for conn in source_item.connections:
            if (
                conn.source is source_item
                and conn.target is target_item
                and conn.source_anchor == source_anchor
                and conn.target_anchor == target_anchor
            ):
                return

        # Captura snapshot ANTES de criar a conexão
        from editor.undo import UndoStack
        before = UndoStack.snapshot(self.scene())

        conn = ConnectionItem(source_item, source_anchor, target_item, target_anchor)
        conn.editor = self.editor
        self.scene().addItem(conn)
        source_item.connections.append(conn)
        target_item.connections.append(conn)

        # Empilha o command de undo APÓS a conexão ser criada
        self.editor.undo_stack.push_snapshot(
            self.scene(),
            self.editor,
            before,
            "Criar conexão",
        )

    def start_temp_connection(self, source_item, source_anchor) -> None:
        """Cria a ConnectionItem temporária (tracejada) de preview de conexão.

        Args:
            source_item: NodeItem de origem da conexão em andamento.
            source_anchor: AnchorItem de saída selecionado.
        """
        self._temp_connection = ConnectionItem(source_item, source_anchor)
        pen = QPen(Qt.GlobalColor.darkGray, 2, Qt.PenStyle.DashLine)
        self._temp_connection.pen = pen
        self._temp_connection.setZValue(-1)
        self.scene().addItem(self._temp_connection)
        source_anchor.setBrush(Qt.GlobalColor.gray)
        source_anchor.update()

    def cleanup_temp_connection(self) -> None:
        """Remove a conexão temporária de preview e restaura o estado do âncora."""
        if self._temp_connection:
            self.scene().removeItem(self._temp_connection)
            self._temp_connection = None
        if self.editor._conn_source_anchor:
            self.editor._conn_source_anchor.setBrush(Qt.GlobalColor.transparent)
            self.editor._conn_source_anchor.update()
        self.editor._connecting = False
        self.editor._conn_source_anchor = None

    # Preview de nó

    def start_node_preview(self) -> None:
        """Instancia o nó pendente como preview semitransparente na cena."""
        if self._preview_node or not self.editor.pending_node:
            return
        desc = self.editor.pending_node
        item = desc.cls(domain=desc.domain)
        item.editor = self.editor
        item.apply_preview_constraints()
        self._preview_node = item
        self.scene().addItem(item)

    def cleanup_node_preview(self) -> None:
        """Remove o nó de preview da cena."""
        if self._preview_node:
            self.scene().removeItem(self._preview_node)
            self._preview_node = None
