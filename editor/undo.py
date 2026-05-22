"""Módulo de undo/redo — a implementar.

Abordagem planejada: padrão Command com QUndoStack do Qt.

Cada operação do editor (adicionar nó, remover conexão, mover item,
alterar propriedade) será encapsulada em uma subclasse de QUndoCommand,
que implementa redo() e undo() de forma atômica.

A QUndoStack será mantida em EditorState e conectada às ações de
Ctrl+Z / Ctrl+Shift+Z já registradas em edit_actions.py.

Referência: https://doc.qt.io/qt-6/qundostack.html
"""

# TODO: implementar QUndoCommand e QUndoStack
