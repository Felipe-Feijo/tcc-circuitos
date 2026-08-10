"""Regressão: NodeItem.remove_anchor() precisa adiar a remoção INTEIRA
(prepare_delete() + scene().removeItem()) como uma única unidade atômica,
não só a remoção física da cena.

Contexto (ver docs/superpowers, sessão de 2026-08-10): remover uma âncora
pilotada conectada (ex.: desligar "piloted" no ReliefValve via diálogo de
propriedades) enquanto o processo está no meio de um evento Qt derrubava
o app com "Windows fatal exception: access violation" num mouseMoveEvent
real subsequente. O crash NUNCA foi reproduzível com QTest sintético --
só com mouse físico real -- e desaparecia ao adicionar qualquer
instrumentação de debug que atrasasse o event loop, a assinatura clássica
de uma condição de corrida sensível a timing dentro do índice espacial
(BSP) da QGraphicsScene.

Mitigação: seguir o EXATO padrão já usado por
editor/delete_manager.py (DeleteManager.do_delete()) -- adiar TUDO via
QTimer.singleShot(0, ...) como uma única unidade (não só o removeItem
isolado, que foi uma primeira tentativa de fix errada: deixava a conexão
"pela metade" -- prepare_delete() já rodado, mas ainda presente na cena
-- exatamente na janela em que push_snapshot()/serialize_scene() podia
tentar serializá-la e estourar AttributeError em conn.source.id).

O segundo teste cobre esse efeito colateral: NodeItem.mouseDoubleClickEvent
também precisa adiar seu push_snapshot() pra depois da remoção assentar.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtCore import QTimer

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.relief_valve import ReliefValve
from graphics.items.base.connections.connection_item import ConnectionItem
from editor.editor_state import EditorState
from editor.mode import EditorMode


def test_remove_anchor_defers_entire_removal_including_prepare_delete():
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

    # Mas NADA na conexão pode ter sido tocado ainda -- nem prepare_delete()
    # (que zeraria source/target), nem a remoção física da cena. A remoção
    # inteira é uma unidade atômica adiada, não uma remoção parcial.
    assert conn.source is node_a
    assert conn.target is node_b
    assert y_anchor.scene() is scene
    assert conn.scene() is scene

    # Só depois do loop de eventos processar (o QTimer.singleShot(0, ...)
    # disparar) é que a remoção inteira deve ter completado.
    app.processEvents()

    assert y_anchor.scene() is None
    assert conn.scene() is None
    assert conn.source is None
    assert conn.target is None


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


def test_dialog_apply_defers_push_snapshot_after_anchor_removal():
    """Reproduz o bug da tentativa de fix anterior: se o snapshot 'depois'
    do undo for capturado ANTES da remoção da conexão assentar,
    serialize_scene() tenta serializar uma conexão com source/target
    zerados e estoura AttributeError. Replica exatamente o que
    NodeItem.mouseDoubleClickEvent() faz (sem precisar de um QDialog.exec()
    modal de verdade)."""
    editor = EditorState()
    editor.mode = EditorMode.SELECT

    scene = QGraphicsScene()

    node_a = ReliefValve(domain="hydraulic")
    node_a.editor = editor
    node_a.properties["p_set"] = 1.5e7
    node_a.properties["piloted"] = True
    node_a.apply_properties()
    scene.addItem(node_a)

    node_b = ReliefValve(domain="hydraulic")
    node_b.editor = editor
    node_b.properties["p_set"] = 1.5e7
    scene.addItem(node_b)

    conn = ConnectionItem(node_a, node_a.anchors["Y"], node_b, node_b.anchors["P"])
    scene.addItem(conn)
    node_a.connections.append(conn)
    node_b.connections.append(conn)

    dialog = node_a.build_properties_dialog()
    dialog._field_piloted.setChecked(False)

    undo_stack = editor.undo_stack
    before = undo_stack.snapshot(scene)

    # Réplica exata do corpo de NodeItem.mouseDoubleClickEvent() após
    # dialog.exec() retornar True.
    node_a.apply_properties_from_dialog(dialog)
    QTimer.singleShot(
        0, lambda: undo_stack.push_snapshot(scene, editor, before, "Editar propriedades")
    )

    # Não deve levantar AttributeError em conn.source.id dentro de
    # serialize_scene() -- a remoção da âncora precisa ter completado
    # ANTES do push_snapshot rodar.
    app.processEvents()

    assert undo_stack.count() == 1
    assert "Y" not in node_a.anchors
    assert conn.scene() is None
