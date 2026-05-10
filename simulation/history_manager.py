from collections import deque


class HistoryManager:
    """Stores snapshots of domain node state for step-backward.

    Each snapshot is a dict[node_id, state_dict].
    """

    def __init__(self, max_history: int = 5):
        self._history: deque = deque(maxlen=max_history)

    def push(self, nodes: dict) -> bool:
        """Save a snapshot.  Returns True if the snapshot was new."""
        snap = {nid: node.get_state() for nid, node in nodes.items()}
        if self._history and snap == self._history[-1]:
            return False
        self._history.append(snap)
        return True

    def pop_and_restore(self, nodes: dict) -> bool:
        """Restore the previous snapshot.  Returns True on success."""
        if len(self._history) <= 1:
            return False
        self._history.pop()
        for node_id, state in self._history[-1].items():
            node = nodes.get(node_id)
            if node:
                node.set_state(state)
        return True

    def can_go_back(self) -> bool:
        return len(self._history) > 1

    def clear(self) -> None:
        self._history.clear()

    def __len__(self) -> int:
        return len(self._history)