class DeleteManager:
    def __init__(self, scene):
        self.scene = scene

    def delete_items(self, items):
        if not items:
            return

        for item in items:
            if hasattr(item, "prepare_delete"):
                item.prepare_delete()
            self.scene.removeItem(item)