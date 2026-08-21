"""Base classes for the simulation domain: Node, Anchor and primitive nodes.

Defines the contract every simulation node must follow and provides the
two simplest pneumatic-domain nodes -- PressureSource and Exhaust --
which don't justify their own files given how trivial they are.
"""

from __future__ import annotations


class Anchor:
    def __init__(self, name: str, node: "Node", domain: str):
        self.node = node
        self.name = name
        self.domain = domain
        self.id = (node.id, name)
        self.connections: list["Connection"] = []

        self.state: bool = False
        self.is_driver: bool = False

        self.type: str | None = None
        self.pressure: float = 0.0
        self.flow: float = 0.0
        self.pressure_var: str | None = None
        self.fault = False
        self.pressurizing = False  # flow conservation not yet reached

    def connect(self, connection: "Connection"):
        if connection not in self.connections:
            self.connections.append(connection)


class Node:
    """Base class for every simulation-domain node.

    Subclasses declare the `node_type` class attribute and call
    `super().__init__` before accessing `self.properties`.

    Simulation contract:
        update(outputs):          called every iteration until stable.
        post_step_update(dt):     called once after convergence.
        handle_command(cmd):      receives the NodeItem.command signal's dict.
        get_state() / set_state(): used by HistoryManager (step_backward).
        get_internal_connections(): returns [(anchor_a, anchor_b), ...].
    """

    def __init__(self, node_id: str, node_type: str, *,
                 domain: str | None = None,
                 properties: dict | None = None,
                 **kwargs):
        self.id = node_id
        self.type = node_type
        self.anchors: dict = {}
        self.domain: str | None = domain
        self.properties: dict = properties or {}

    def add_anchor(self, name, domain) -> Anchor:
        anchor = Anchor(name, self, domain)
        self.anchors[name] = anchor
        return anchor

    def get_anchor(self, name):
        return self.anchors[name]

    def get_state(self) -> dict:
        """Serializes the current state of every anchor for a snapshot.

        Returns:
            Dict with each anchor's state, including pressure and flow
            for hydraulic-domain anchors.
        """
        anchors_state = {}
        for name, anchor in self.anchors.items():
            anchor_data = {"state": anchor.state}
            if anchor.domain == "hydraulic":
                anchor_data["pressure"] = anchor.pressure
                anchor_data["flow"]     = anchor.flow
                anchor_data["fault"]    = getattr(anchor, "fault", False)
            anchors_state[name] = anchor_data

        return {"anchors": anchors_state}

    def set_state(self, state: dict):
        """Restores anchor state from a snapshot.

        Args:
            state: Dict in the format returned by get_state().
        """
        for name, anchor_data in state.get("anchors", {}).items():
            anchor = self.anchors.get(name)
            if not anchor:
                continue
            anchor.state = anchor_data.get("state", anchor.state)
            if anchor.domain == "hydraulic":
                anchor.pressure = anchor_data.get("pressure", anchor.pressure)
                anchor.flow     = anchor_data.get("flow", anchor.flow)
                anchor.fault    = anchor_data.get("fault", False)

    def handle_command(self, command: str):
        """Receives an external command (UI, test or debug). No-op by default."""
        pass

    def update(self, outputs=None):
        """Updates the node's internal state from the previous iteration's outputs.

        Called by the SimulationEngine every iteration until
        stabilization. Nodes with no dynamics of their own don't need
        to override this method.
        """
        pass

    def post_step_update(self, dt):
        """Run once after the step stabilizes.

        Used for sensors, delays and physical-state commits.

        Args:
            dt: Time interval in seconds since the last step.
        """
        pass

    def get_internal_connections(self):
        """Returns the node's internal connections between its own anchors.

        Returns:
            List of (anchor_a, anchor_b) tuples. Returns an empty list by default.
        """
        return []

    def get_visual_state(self):
        return None


class PressureSource(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="pressure_source", **kwargs)

    def update(self, outputs=None):
        self.get_anchor("P").state = True
        self.get_anchor("P").is_driver = True


class Exhaust(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="exhaust", **kwargs)

    def update(self, outputs=None):
        self.get_anchor("R").state = False
        self.get_anchor("R").is_driver = True


class Junction(Node):
    """Junction node: a branch point on a wire/pipe, with no dynamics of
    its own.

    Single anchor, named "J". Electric/hydraulic/pneumatic fan-out
    happens for free -- `Anchor.connections` is already a list, so
    linking 3+ Connections to the same Anchor is enough. No overrides
    needed: `update()` and `get_internal_connections()` inherited from
    Node are already no-op/[]."""

    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="junction", **kwargs)
