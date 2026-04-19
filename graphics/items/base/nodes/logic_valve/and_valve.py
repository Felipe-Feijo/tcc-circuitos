from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QRectF


from graphics.items.base.nodes.node_item import NodeItem
from .....anchors.anchor import AnchorItem


class AndValve(NodeItem):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


        self.node_type = "and_valve"

        self.icon_default = QPixmap("resources/nodes/and_valve/and_valve_default.png")
        self.icon_x_side = QPixmap("resources/nodes/and_valve/and_valve_right.png")
        self.icon_y_side = QPixmap("resources/nodes/and_valve/and_valve_left.png")

        self.pixmap = self.icon_default

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.add_anchor(AnchorItem("X", QPointF(0, self.height*90/165), node=self, domain=self.domain, exit_directions={"external": ["left"]}))
        self.add_anchor(AnchorItem("Y", QPointF(self.width, self.height*90/165), node=self, domain=self.domain, exit_directions={"external": ["right"]}))
        self.add_anchor(AnchorItem("A", QPointF(self.width*0.5, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))


    def update_from_domain(self, domain_node):
        super().update_from_domain(domain_node)
        state = domain_node.get_visual_state()
        if state == "default":
            self.pixmap = self.icon_default
        elif state == "X":
            self.pixmap = self.icon_x_side
        elif state == "Y":
            self.pixmap = self.icon_y_side
        self.update()
            
        


    


    

