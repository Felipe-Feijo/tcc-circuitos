"""Registro automático de todos os tipos de nó disponíveis na paleta.

Em vez de listar cada nó manualmente, este módulo percorre o pacote
``graphics.items.base.nodes`` e coleta todas as classes que declaram
``palette_meta()`` retornando uma instância de ``PaletteMeta``.

Para adicionar um novo nó à paleta basta:
    1. Criar a classe em ``graphics/items/base/nodes/``.
    2. Declarar o classmethod ``palette_meta()`` retornando um ``PaletteMeta``
       com os domínios, sprite e nome desejados.

Nenhuma alteração neste arquivo é necessária.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import graphics.items.base.nodes as _nodes_pkg
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import NodeDescriptor, PaletteMeta
from graphics.utils.pixmap_utils import generate_pixmap_for_palette


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _discover_palette_nodes() -> list[type]:
    """Retorna todas as classes concretas de NodeItem com ``palette_meta()`` definido.

    Percorre recursivamente todos os arquivos ``.py`` sob o diretório do pacote
    ``graphics.items.base.nodes``, importa cada módulo e coleta as subclasses de
    ``NodeItem`` que retornam um ``PaletteMeta`` não-nulo.

    Usa ``os.walk`` em vez de ``pkgutil.walk_packages`` porque os subdiretórios
    não possuem ``__init__.py`` e portanto não são reconhecidos como subpacotes
    pelo sistema de importação padrão.
    """
    import os

    pkg_dir = Path(_nodes_pkg.__file__).parent
    pkg_root = pkg_dir.parent  # graphics/items/base/
    # raiz do projeto (para montar o module_name correto)
    project_root = pkg_root
    for _ in range(3):          # sobe graphics/ → items/ → base/ → project root
        project_root = project_root.parent

    seen: set[type] = set()
    result: list[type] = []

    for dirpath, _dirs, filenames in os.walk(pkg_dir):
        for filename in filenames:
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            abs_path = Path(dirpath) / filename
            # converte caminho de arquivo em nome de módulo
            rel = abs_path.relative_to(project_root).with_suffix("")
            module_name = ".".join(rel.parts)

            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue

            for _name, cls in inspect.getmembers(module, inspect.isclass):
                if (
                    cls not in seen
                    and issubclass(cls, NodeItem)
                    and cls is not NodeItem
                    and cls.palette_meta() is not None
                ):
                    seen.add(cls)
                    result.append(cls)

    return result


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_nodes(palette, on_add_node) -> None:
    """Popula a paleta com todos os nós descobertos automaticamente.

    Os nós são agrupados por domínio (seção da paleta) e ordenados
    alfabeticamente pelo nome exibido dentro de cada seção.

    Args:
        palette:      Objeto de paleta com ``palette.sections[domain]``.
        on_add_node:  Callback chamado ao clicar num nó; recebe um
                      ``NodeDescriptor``.
    """
    # Agrupa por domínio para poder ordenar alfabeticamente dentro de cada seção.
    by_domain: dict[str, list[tuple[type, PaletteMeta]]] = {}

    for cls in _discover_palette_nodes():
        meta: PaletteMeta = cls.palette_meta()
        for domain in meta.domains:
            section_key = domain.capitalize()
            if section_key not in palette.sections:
                continue
            by_domain.setdefault(section_key, []).append((cls, meta))

    for section_key, entries in by_domain.items():
        entries.sort(key=lambda t: (t[1].name or t[0].__name__).lower())  # ordem alfabética
        section = palette.sections[section_key]
        for cls, meta in entries:
            display_name = meta.name or cls.__name__
            pixmap = generate_pixmap_for_palette(meta.sprite)
            # captura de variáveis por default-argument evita o late-binding clássico
            section.add_node(
                name=display_name,
                pixmap=pixmap,
                callback=lambda c=cls, d=section_key.lower():
                    on_add_node(NodeDescriptor(c, domain=d)),
            )
