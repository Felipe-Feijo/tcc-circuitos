"""Define os modos de interação do editor de diagramas."""

from enum import Enum


class EditorMode(Enum):
    """Modos de interação disponíveis no editor.

    Attributes:
        SELECT:   Seleção e movimentação de itens.
        ADD:      Posicionamento de novo nó a partir da paleta.
        CONNECT:  Criação de conexão entre dois âncoras.
        SIMULATE: Execução da simulação; edição desabilitada.
    """

    SELECT = None
    ADD = "add"
    CONNECT = "connect"
    SIMULATE = "simulate"
