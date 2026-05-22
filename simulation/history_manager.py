"""Armazena snapshots do estado de domínio para suportar step_backward."""

from collections import deque


class HistoryManager:
    """Mantém um histórico de snapshots do estado dos nós de domínio.

    Cada snapshot é um dicionário {node_id: state_dict}, gerado via
    Node.get_state() e restaurado via Node.set_state().

    Snapshots idênticos ao anterior não são armazenados (sem mudança de estado).

    Args:
        max_history: Número máximo de snapshots mantidos em memória.
    """

    def __init__(self, max_history: int = 5):
        self._history: deque = deque(maxlen=max_history)

    def push(self, nodes: dict) -> bool:
        """Salva um snapshot do estado atual dos nós.

        Args:
            nodes: Dicionário {node_id: Node} do engine.

        Returns:
            True se o snapshot foi salvo, False se idêntico ao anterior.
        """
        snap = {nid: node.get_state() for nid, node in nodes.items()}
        if self._history and snap == self._history[-1]:
            return False
        self._history.append(snap)
        return True

    def pop_and_restore(self, nodes: dict) -> bool:
        """Remove o snapshot atual e restaura o anterior.

        Args:
            nodes: Dicionário {node_id: Node} do engine.

        Returns:
            True se a restauração ocorreu, False se não há histórico suficiente.
        """
        if len(self._history) <= 1:
            return False
        self._history.pop()
        for node_id, state in self._history[-1].items():
            node = nodes.get(node_id)
            if node:
                node.set_state(state)
        return True

    def can_go_back(self) -> bool:
        """Retorna True se há pelo menos dois snapshots (pode retroceder um passo)."""
        return len(self._history) > 1

    def clear(self) -> None:
        """Remove todos os snapshots do histórico."""
        self._history.clear()

    def __len__(self) -> int:
        return len(self._history)
