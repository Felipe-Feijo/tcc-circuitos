from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from editor.editor_controller import EditorController
from simulation.simulation_engine import SimulationEngine
from simulation.simulation_controller import SimulationController


class SimulationSession:
    """
    Owns the lifecycle of a simulation run.

    Responsibilities:
    - Build the domain graph from the current scene
    - Create and own SimulationEngine + SimulationController
    - Bind / unbind graphical items to the simulation
    - Control start / stop semantics
    """

    def __init__(self, scene):
        self.scene = scene
        self.engine = None
        self.controller = None
        self.active = False

    def start(self):
        if self.active:
            return

        # 1️⃣ Build domain graph
        editor = EditorController(self.scene)
        builder = editor.build_graph()

        # 2️⃣ Create engine + controller
        self.engine = SimulationEngine(
            nodes=builder.nodes,
            connections=builder.connections
        )

        self.controller = SimulationController(self.engine)
        self.controller.on_update_node = builder.node_map
        self.controller.on_update_connection = builder.connection_map

        # 3️⃣ Bind graphical items to simulation
        self._activate_node_items()

        # 4️⃣ Initial solve
        self.controller.step()

        self.active = True

    def stop(self):
        if not self.active:
            return

        self._deactivate_node_items()

        self.engine = None
        self.controller = None
        self.active = False

    # ---------------------------
    # Internal helpers
    # ---------------------------

    def _activate_node_items(self):
        for item in self.scene.items():
            if not isinstance(item, NodeItem):
                continue

            item.simulation_mode = True
            item.command.connect(self.controller.command)

    def _deactivate_node_items(self):
        for item in self.scene.items():
            if isinstance(item, NodeItem):
                
                item.reset_visual_state()

                try:
                    item.command.disconnect(self.controller.command)
                except TypeError:
                    # already disconnected or never connected
                    pass
            elif isinstance(item, ConnectionItem):
                item.reset_visual_state()
