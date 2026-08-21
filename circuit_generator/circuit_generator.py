"""Orchestrates the automatic generation of pneumatic circuits.

Main entry point of the generator: parses the sequence, selects the
generation method, applies the spatial layout and loads the result
into the graphics scene.
"""

from circuit_generator.sequence_parser import parse
from circuit_generator import layout_engine, step_by_step_layout, cascade_layout, step_by_step_electric_layout
from circuit_generator.methods import cascade, step_by_step_pneumatic, step_by_step_electric
from persistence.serializer import deserialize_scene
from graphics.sensor_registry.sensor_registry import SensorRegistry


METHOD_MAP = {
    ("cascade",      None):          cascade.generate,
    ("step_by_step", "pneumatic"):   step_by_step_pneumatic.generate,
    ("step_by_step", "electric"):    step_by_step_electric.generate,
}

LAYOUT_MAP = {
    ("cascade",      None):          cascade_layout.apply,
    ("step_by_step", "pneumatic"):   step_by_step_layout.apply,
    ("step_by_step", "electric"):    step_by_step_electric_layout.apply,
}


def generate_and_load(sequence: str, method: str, sub_type: str | None, scene, editor) -> None:
    """Generates a circuit from the sequence and loads it into the graphics scene.

    Args:
        sequence: Cylinder actuation sequence (e.g. "A+B-A-B+").
        method: Generation method -- "cascade" or "step_by_step".
        sub_type: Method sub-type -- "pneumatic", "electric" or None.
        scene: Destination QGraphicsScene.
        editor: EditorState passed to the created items.

    Raises:
        ValueError: If the sequence is invalid or the method isn't recognized.
    """
    events = parse(sequence)

    generator = METHOD_MAP.get((method, sub_type))
    if generator is None:
        raise ValueError(f"Unknown method: method={method!r}, sub_type={sub_type!r}")

    data = generator(events)   # returns dict with _role on the nodes

    apply_layout = LAYOUT_MAP.get((method, sub_type))
    if apply_layout is None:
        raise ValueError(
            f"Layout not implemented for method={method!r}, "
            f"sub_type={sub_type!r}"
        )
    apply_layout(data)         # fills in position.x/y and removes _role

    scene.sensor_registry = SensorRegistry()
    with scene.sensor_registry.loading():
        deserialize_scene(data, scene, editor, clear_scene=True)

    if hasattr(editor, "fit_scene"):
        editor.fit_scene()
