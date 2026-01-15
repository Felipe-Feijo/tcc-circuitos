from domain.connections import Connection
from domain.components import Component


def print_graph(components, connections):
    print("\n=== COMPONENTS ===")
    for comp in components:
        print(f"Component {comp.id} ({comp.type})")
        for anchor in comp.anchors.values():
            connected = [
                f"{c.a.id if c.b == anchor else c.b.id}"
                for c in anchor.connections
            ]
            print(f"  Anchor {anchor.name} -> {connected}")

    print("\n=== CONNECTIONS ===")
    for conn in connections:
        print(f"{conn.a.id} <--> {conn.b.id}")


def main():
    # Criando componentes genéricos
    valve = Component(
        component_id="valve_1",
        comp_type="generic",
        anchor_names=["P", "A", "B", "T"]
    )

    cylinder = Component(
        component_id="cylinder_1",
        comp_type="generic",
        anchor_names=["A", "B"]
    )

    atm = Component(
        component_id="atm",
        comp_type="generic",
        anchor_names=["IN"]
    )

    # Criando conexões
    connections = [
        Connection(valve.get_anchor("P"), atm.get_anchor("IN")),
        Connection(valve.get_anchor("A"), cylinder.get_anchor("A")),
        Connection(valve.get_anchor("B"), cylinder.get_anchor("B")),
        Connection(valve.get_anchor("T"), atm.get_anchor("IN")),
    ]

    # Inspecionando
    print_graph([valve, cylinder, atm], connections)


if __name__ == "__main__":
    main()
