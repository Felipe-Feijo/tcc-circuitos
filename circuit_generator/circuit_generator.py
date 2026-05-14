from circuit_generator.sequence_parser import parse
from circuit_generator.layout_engine import apply as apply_layout
from circuit_generator.methods import cascade, step_by_step_pneumatic, step_by_step_electric
from persistence.serializer import deserialize_scene
from graphics.sensor_registry.sensor_registry import SensorRegistry


METHOD_MAP = {
    ("cascade",      None):          cascade.generate,
    ("step_by_step", "pneumatic"):   step_by_step_pneumatic.generate,
    ("step_by_step", "electric"):    step_by_step_electric.generate,
}


def generate_and_load(sequence: str, method: str, sub_type: str | None, scene, editor):
    events = parse(sequence)

    generator = METHOD_MAP.get((method, sub_type))
    if generator is None:
        raise ValueError(f"Método desconhecido: method={method!r}, sub_type={sub_type!r}")

    data = generator(events)   # retorna dict com _role nos nós
    apply_layout(data)         # preenche position.x/y e remove _role

    scene.sensor_registry = SensorRegistry()
    with scene.sensor_registry.loading():
        deserialize_scene(data, scene, editor, clear_scene=True)

    if hasattr(editor, "fit_scene"):
        editor.fit_scene()