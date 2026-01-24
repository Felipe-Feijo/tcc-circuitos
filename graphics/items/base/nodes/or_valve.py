from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QRectF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class OrValve(NodeItem):

    def __init__(self):
        super().__init__()


        self.node_type = "or_valve"

        self.icon_x_side = QPixmap("resources/nodes/or_valve/or_valve_x_side.png")
        self.icon_y_side = QPixmap("resources/nodes/or_valve/or_valve_y_side.png")
        #self.icon_pressed = QPixmap("resources/nodes/or_valve/or_valve_pressed.png")

        self.pixmap = self.icon_x_side

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.add_anchor(AnchorItem("X", QPointF(0, self.height*0.5429), node=self))
        self.add_anchor(AnchorItem("Y", QPointF(self.width, self.height*0.5429), node=self))
        self.add_anchor(AnchorItem("A", QPointF(self.width*0.5039, 0), node=self))


    def update_from_domain(self, domain_node):
        print("received")
        state = domain_node.get_visual_state()
        if state == "X":
            self.pixmap = self.icon_x_side
        elif state == "Y":
            self.pixmap = self.icon_y_side
        self.update()
            
        


    


    

