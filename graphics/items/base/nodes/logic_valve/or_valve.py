from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QRectF
from simulation.nodes.logic_valve.or_valve import OrValve as OrValveNode


from graphics.items.base.nodes.node_item import NodeItem
from .....anchors.anchor import AnchorItem


class OrValve(NodeItem):
    node_type = "or_valve"
    simulation_cls = OrValveNode

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)



        self.icon_x_side = QPixmap("resources/nodes/or_valve/or_valve_x_side.png")
        self.icon_y_side = QPixmap("resources/nodes/or_valve/or_valve_y_side.png")

        self.pixmap = self.icon_x_side

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.add_anchor(AnchorItem("X", QPointF(0, self.height*0.5429), node=self, domain=self.domain, exit_directions={"external": ["left"]}))
        self.add_anchor(AnchorItem("Y", QPointF(self.width, self.height*0.5429), node=self, domain=self.domain, exit_directions={"external": ["right"]}))
        self.add_anchor(AnchorItem("A", QPointF(self.width*0.5039, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))


    def update_from_domain(self, domain_node):
        super().update_from_domain(domain_node)
        state = domain_node.get_visual_state()
        if state == "X":
            self.pixmap = self.icon_x_side
        elif state == "Y":
            self.pixmap = self.icon_y_side
        self.update()
            
        


    


    

