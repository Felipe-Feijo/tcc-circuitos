"""Gerencia a remoção segura de nós, conexões e labels da cena gráfica."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGraphicsScene

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from graphics.labels.label import LabelItem


class DeleteManager:
    """Remove itens da cena de forma segura, adiando a deleção para fora do ciclo de eventos Qt.

    A deleção imediata durante o processamento de um evento pode causar
    acesso a ponteiros inválidos. O uso de QTimer.singleShot(0, ...) garante
    que a remoção ocorre apenas após o evento atual ser completamente processado.
    """

    def __init__(self, scene):
        self.scene = scene

    def delete_selection(self, editor_state=None) -> bool:
        """Remove os itens atualmente selecionados da cena.

        Waypoints de conexão têm prioridade: se alguma conexão tiver um
        waypoint selecionado, apenas esse waypoint é removido. Caso contrário,
        remove todos os nós, conexões e labels selecionados, incluindo as
        conexões transitivas dos nós selecionados.

        Args:
            editor_state: EditorState opcional. Quando fornecido, a operação
                é registrada na undo_stack para suporte a Ctrl+Z.

        Returns:
            True se algum item foi removido, False se não havia seleção.
        """
        # Waypoints têm prioridade: a conexão fica desselecionada ao clicar
        # num waypoint, então varremos todos os itens da cena, não só os selecionados.
        for item in self.scene.items():
            if isinstance(item, ConnectionItem) and getattr(item, '_selected_wp', None) is not None:
                item._delete_waypoint(item._selected_wp)
                return True

        items = list(self.scene.selectedItems())

        if not items:
            return False

        # Captura snapshot ANTES da deleção para undo
        before = None
        if editor_state is not None:
            from editor.undo import UndoStack
            before = UndoStack.snapshot(self.scene)

        connections = {i for i in items if isinstance(i, ConnectionItem)}
        nodes       = [i for i in items if isinstance(i, NodeItem)]
        labels      = [i for i in items if isinstance(i, LabelItem)]

        # Inclui conexões dos nós selecionados (serão removidas junto)
        for node in nodes:
            connections.update(getattr(node, "connections", []))

        connections = list(connections)

        def do_delete():
            """Executa a remoção efetiva, adiada para fora do evento Qt."""
            for label in labels:
                parent = label.parentItem()
                if parent and hasattr(parent, "labels"):
                    key = next((k for k, v in parent.labels.items() if v is label), None)
                    if key:
                        parent.labels.pop(key)
                if label.scene():
                    self.scene.removeItem(label)

            # Fase 1: notifica cada item antes de remover (limpa referências internas)
            for conn in connections:
                conn.prepare_delete()

            for node in nodes:
                node.prepare_delete()

            # Fase 2: remove da cena
            for item in connections + nodes:
                if item.scene():
                    self.scene.removeItem(item)

            connections.clear()
            nodes.clear()
            items.clear()

            # Força atualização visual completa da cena
            self.scene.invalidate(
                self.scene.sceneRect(),
                QGraphicsScene.SceneLayer.AllLayers
            )
            current_index = self.scene.itemIndexMethod()
            self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
            self.scene.setItemIndexMethod(current_index)
            self.scene.update()

            # Empilha o command de undo APÓS a deleção ser aplicada
            if editor_state is not None and before is not None:
                editor_state.undo_stack.push_snapshot(
                    self.scene,
                    editor_state,
                    before,
                    "Deletar itens",
                )

        QTimer.singleShot(0, do_delete)
        return True
