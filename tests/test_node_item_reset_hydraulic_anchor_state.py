"""Reprodução: labels de pressão/vazão hidráulicas e setas de fluxo das
conexões continuavam mostrando o último valor simulado depois de sair da
simulação.

Causa raiz: NodeItem.reset_visual_state() nunca zerava anchor.pressure/
anchor.flow (só update_from_domain() os escrevia, a cada passo). As setas
de fluxo em ConnectionItem._draw_flow_arrows() e o texto de
AnchorItem._label_hydraulic são lidos diretamente desses dois atributos,
então ambos ficavam presos no valor do último passo simulado."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.check_valve.check_valve import CheckValve


def test_reset_visual_state_zeroes_hydraulic_anchor_pressure_and_flow():
    node = CheckValve(domain="hydraulic")
    anchor = node.anchors["X"]
    anchor.pressure = 1.5e7
    anchor.flow = 3.2e-4
    anchor.update_hydraulic_labels()
    assert "1.5e" in anchor._label_hydraulic.toPlainText() or "15" in anchor._label_hydraulic.toPlainText()

    node.reset_visual_state()

    assert anchor.pressure == 0.0
    assert anchor.flow == 0.0
    assert anchor._label_hydraulic.toPlainText() == "0 Pa | 0 m³/s"
