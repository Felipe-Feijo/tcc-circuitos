
from simulation.simulation_engine import SimulationEngine


class SimulationController:
    def __init__(self, engine: SimulationEngine):
        self.engine = engine
        self.on_update_node = None  # dict[NodeItem, DomainNode]
        self.on_update_connection = None  # dict[ConnectionItem → Connection]

    def command(self, node_id: str, cmd: str):
        node = self.engine.nodes.get(node_id)
        if not node:
            print(f"Node {node_id} not found")
            return

        node.handle_command(cmd)
        self.step()

    def step(self):
        print("starting simulation step")
        # 1. Resolve o sistema até convergir
        self.engine.run_until_stable()

        if self.on_update_node:
            for node_item, domain_node in self.on_update_node.items():
                if domain_node.type == "piston":
                    node_item.set_extended(domain_node.position == 1)

        if self.on_update_connection:
            for conn_item, domain_conn in self.on_update_connection.items():
                conn_item.set_pressurized(domain_conn.is_pressurized())
        print("step complete")