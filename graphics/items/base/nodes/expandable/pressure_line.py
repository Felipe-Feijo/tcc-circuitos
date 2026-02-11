from graphics.items.base.nodes.expandable.expandable_item import ExpandableItem


class PressureLine(ExpandableItem):
    TERMINAL_VISUALS = {
        "left":  "resources/nodes/pressure_line/pressure_line_terminal.png",
        "right": "resources/nodes/pressure_line/pressure_line_terminal.png"
    }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_type = "pressure_line"
