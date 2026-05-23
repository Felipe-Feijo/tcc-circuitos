"""Módulo de undo/redo — padrão Command com QUndoStack do Qt.

Cada operação do editor (adicionar nó, remover, mover, conectar, colar)
é encapsulada em um SceneSnapshotCommand que armazena snapshots JSON da
cena antes e depois da operação.

Uso típico:
    before = undo_stack.snapshot(scene)   # ANTES da operação
    # ... executa a operação ...
    undo_stack.push_snapshot(scene, editor_state, before, "Descrição")

Referência: https://doc.qt.io/qt-6/qundostack.html
"""

import copy

from PyQt6.QtGui import QUndoCommand, QUndoStack

from persistence.serializer import serialize_scene, deserialize_scene


def _restore_snapshot(snapshot: dict, scene, editor_state) -> None:
    """Restaura a cena a partir de um snapshot, reiniciando o SensorRegistry."""
    from graphics.sensor_registry.sensor_registry import SensorRegistry

    scene.sensor_registry = SensorRegistry()
    with scene.sensor_registry.loading():
        deserialize_scene(
            copy.deepcopy(snapshot),
            scene,
            editor_state,
            clear_scene=True,
        )


class SceneSnapshotCommand(QUndoCommand):
    """Command genérico baseado em snapshot completo da cena.

    O primeiro redo() é suprimido porque QUndoStack.push() o chama
    imediatamente — mas nesse momento a operação já foi aplicada à cena,
    então reaplicar o snapshot 'after' destruiria o estado em memória.
    A partir do segundo redo() em diante (verdadeiro redo do usuário),
    o snapshot é restaurado normalmente.
    """

    def __init__(self, scene, editor_state, before: dict, after: dict, text: str):
        super().__init__(text)
        self._scene = scene
        self._editor = editor_state
        self._before = before
        self._after = after
        self._first_redo = True  # suprime a chamada automática do push()

    def undo(self) -> None:
        _restore_snapshot(self._before, self._scene, self._editor)

    def redo(self) -> None:
        if self._first_redo:
            # push() chama redo() automaticamente — a cena já tem o estado
            # correto, não precisamos (nem devemos) restaurar o snapshot.
            self._first_redo = False
            return
        _restore_snapshot(self._after, self._scene, self._editor)


class UndoStack(QUndoStack):
    """QUndoStack estendida com helpers para snapshots de cena."""

    @staticmethod
    def snapshot(scene) -> dict:
        """Serializa a cena em um dict. Deve ser chamado *antes* da operação."""
        return serialize_scene(scene)

    def push_snapshot(self, scene, editor_state, before: dict, text: str) -> None:
        """Captura o estado atual como 'after' e empilha o command.

        Deve ser chamado *depois* que a operação foi aplicada à cena.
        """
        after = serialize_scene(scene)
        cmd = SceneSnapshotCommand(scene, editor_state, before, after, text)
        self.push(cmd)
