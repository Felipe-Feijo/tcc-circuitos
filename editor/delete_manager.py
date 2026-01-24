from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGraphicsScene

class DeleteManager:
    def __init__(self, scene):
        self.scene = scene

    def delete_selection(self):
        items = list(self.scene.selectedItems())
        if not items:
            return False

        def do_delete():
            print(">>> Executing deferred delete")

            for item in items:
                if hasattr(item, "prepare_delete"):
                    item.prepare_delete()

                if item.scene():
                    self.scene.removeItem(item)

            # 🔴 ESSENCIAL
            self.scene.invalidate(
                self.scene.sceneRect(),
                QGraphicsScene.SceneLayer.AllLayers
            )
            self.scene.update()

        QTimer.singleShot(0, do_delete)
        return True