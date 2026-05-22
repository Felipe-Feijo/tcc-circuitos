"""Orquestra a geração automática de circuitos pneumáticos.

Ponto de entrada principal do gerador: faz o parse da sequência,
seleciona o método de geração, aplica o layout espacial e carrega
o resultado na cena gráfica.
"""

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


def generate_and_load(sequence: str, method: str, sub_type: str | None, scene, editor) -> None:
    """Gera um circuito a partir da sequência e carrega na cena gráfica.

    Args:
        sequence: Sequência de atuação dos cilindros (ex: "A+B-A-B+").
        method: Método de geração — "cascade" ou "step_by_step".
        sub_type: Subtipo do método — "pneumatic", "electric" ou None.
        scene: QGraphicsScene de destino.
        editor: EditorState passado aos itens criados.

    Raises:
        ValueError: Se a sequência for inválida ou o método não for reconhecido.
    """
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
