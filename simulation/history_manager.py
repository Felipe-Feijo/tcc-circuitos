"""Stores domain-state snapshots to support step_backward."""

from collections import deque


class HistoryManager:
    """Keeps a history of domain node state snapshots.

    Each snapshot is a {node_id: state_dict} dict, generated via
    Node.get_state() and restored via Node.set_state().

    Snapshots identical to the previous one aren't stored (no state change).

    Args:
        max_history: Maximum number of snapshots kept in memory.
    """

    def __init__(self, max_history: int = 5):
        self._history: deque = deque(maxlen=max_history)

    def push(self, nodes: dict) -> bool:
        """Saves a snapshot of the nodes' current state.

        Args:
            nodes: The engine's {node_id: Node} dict.

        Returns:
            True if the snapshot was saved, False if identical to the previous one.
        """
        snap = {nid: node.get_state() for nid, node in nodes.items()}
        if self._history and snap == self._history[-1]:
            return False
        self._history.append(snap)
        return True

    def pop_and_restore(self, nodes: dict) -> bool:
        """Removes the current snapshot and restores the previous one.

        Args:
            nodes: The engine's {node_id: Node} dict.

        Returns:
            True if the restore happened, False if there isn't enough history.
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
        """Returns True if there are at least two snapshots (can step back one)."""
        return len(self._history) > 1

    def clear(self) -> None:
        """Removes every snapshot from the history."""
        self._history.clear()

    def __len__(self) -> int:
        return len(self._history)
