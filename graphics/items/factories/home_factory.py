from graphics.items.base.nodes.component_item import ComponentItem

def create_home_component(editor):
    w, h = 80, 40
    item = ComponentItem(
        w, h,
        icon_path="resources/components/component_item/home.png"
    )
    item.editor = editor
    return item