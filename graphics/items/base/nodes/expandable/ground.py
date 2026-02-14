from graphics.items.base.nodes.expandable.expandable_item import ExpandableItem


class Ground(ExpandableItem):
    TERMINAL_VISUALS = {
        "left":  "resources/nodes/ground/ground_terminal.png",
    }
    DEFAULT_ANCHORS = ["X1"]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_type = "ground"

    def paint_symbol(self, painter):
        if not self.pixmap_left:
            return

        painter.drawPixmap(0, 0, self.pixmap_left)

    def layout_anchors(self):
        x0 = self.pix_w * 0.5
        y0 = 0

        for i, anchor in enumerate(self.anchor_list):
            br = anchor.boundingRect()
            cx = x0 + i * self.spacing
            cy = y0

            anchor.setPos(
                cx - br.center().x(),
                cy - br.center().y()
            )