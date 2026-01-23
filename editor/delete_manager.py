class DeleteManager:
    def __init__(self, scene):
        self.scene = scene

    def delete_items(self, items):
        if not items:
            return False

        for item in items:
            if hasattr(item, "prepare_delete"):
                item.prepare_delete()
            self.scene.removeItem(item)

        return True

    def delete_selection(self):
        return self.delete_items(self.scene.selectedItems())