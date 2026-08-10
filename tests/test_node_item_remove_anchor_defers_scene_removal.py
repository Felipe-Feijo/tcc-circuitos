"""Regressão: NodeItem.remove_anchor() não pode remover a âncora e sua
conexão da cena de forma síncrona.

Contexto: quando remove_anchor() roda dentro do call stack de um evento Qt
ativo (ex.: o botão OK de um PropertiesDialog, que dispara
apply_properties_from_dialog -> ..._update_pilot_anchor -> remove_anchor),
remover itens da cena de forma imediata pode deixar a árvore de itens (ou
o estado de hover/grab) com um ponteiro C++ inválido, travando o processo
com "Windows fatal exception: access violation" no próximo
mouseMoveEvent -- mesmo padrão já documentado e evitado em
editor/delete_manager.py via QTimer.singleShot(0, ...).

Ver docs/superpowers (sessão de 2026-08-10) para o relato original do
crash: ativar a pilotagem (Y conectado) e depois desativá-la via diálogo
de propriedades derrubava o app.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.relief_valve import ReliefValve
from graphics.items.base.connections.connection_item import ConnectionItem


def test_remove_anchor_defers_scene_removal_of_connected_anchor_and_connection():
    scene = QGraphicsScene()

    node_a = ReliefValve(domain="hydraulic")
    node_a.properties["piloted"] = True
    node_a.apply_properties()
    scene.addItem(node_a)

    node_b = ReliefValve(domain="hydraulic")
    scene.addItem(node_b)

    conn = ConnectionItem(node_a, node_a.anchors["Y"], node_b, node_b.anchors["P"])
    scene.addItem(conn)
    node_a.connections.append(conn)
    node_b.connections.append(conn)

    y_anchor = node_a.anchors["Y"]

    # Desliga a pilotagem -- por baixo dos panos isto chama remove_anchor("Y").
    node_a.properties["piloted"] = False
    node_a.apply_properties()

    # A contabilidade lógica (dict de âncoras) já reflete a remoção de imediato.
    assert "Y" not in node_a.anchors

    # Mas a remoção física da cena precisa ter sido adiada -- não pode ter
    # acontecido de forma síncrona dentro desta mesma chamada, enquanto
    # ainda estamos "dentro" do evento que disparou apply_properties().
    assert y_anchor.scene() is scene
    assert conn.scene() is scene

    # Só depois do loop de eventos processar (o próprio QTimer.singleShot(0, ...)
    # disparar) é que a remoção física deve ter completado.
    app.processEvents()

    assert y_anchor.scene() is None
    assert conn.scene() is None


def test_remove_anchor_without_connection_still_removes_after_event_loop():
    """Sem nenhuma conexão viva, o comportamento observável (âncora some
    da cena eventualmente) precisa continuar valendo -- só o timing muda."""
    scene = QGraphicsScene()

    node = ReliefValve(domain="hydraulic")
    node.properties["piloted"] = True
    node.apply_properties()
    scene.addItem(node)

    y_anchor = node.anchors["Y"]

    node.properties["piloted"] = False
    node.apply_properties()

    assert "Y" not in node.anchors

    app.processEvents()

    assert y_anchor.scene() is None
