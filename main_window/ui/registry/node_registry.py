"""Automatic registry of every node type available in the palette.

Instead of listing each node manually, this module walks the
``graphics.items.base.nodes`` package and collects every class that
declares ``palette_meta()`` returning a ``PaletteMeta`` instance.

To add a new node to the palette, just:
    1. Create the class under ``graphics/items/base/nodes/``.
    2. Declare the ``palette_meta()`` classmethod returning a
       ``PaletteMeta`` with the desired domains, sprite and name.

No change to this file is needed.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import NodeDescriptor, PaletteMeta
from paths import get_base_dir


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _discover_palette_nodes() -> list[type]:
    """Returns every concrete NodeItem class with ``palette_meta()`` defined.

    Recursively walks every ``.py`` file under the
    ``graphics.items.base.nodes`` package directory, imports each
    module and collects the ``NodeItem`` subclasses that return a
    non-null ``PaletteMeta``.

    Uses ``os.walk`` instead of ``pkgutil.walk_packages`` because the
    subdirectories have no ``__init__.py`` and therefore aren't
    recognized as subpackages by the standard import system.
    """
    import os

    # `graphics.items.base.nodes.__file__` doesn't point to a real path
    # in frozen builds (PyInstaller) -- uses the same base directory
    # resolved for everything else (dev: project root; frozen: where
    # the --add-data payload was extracted).
    project_root = get_base_dir()
    pkg_dir = project_root / "graphics" / "items" / "base" / "nodes"

    seen: set[type] = set()
    result: list[type] = []

    for dirpath, _dirs, filenames in os.walk(pkg_dir):
        for filename in filenames:
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            abs_path = Path(dirpath) / filename
            # converts a file path into a module name
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
    """Populates the palette with every automatically discovered node.

    Nodes are grouped by domain (palette section) and sorted
    alphabetically by display name within each section.

    Args:
        palette:      Palette object with ``palette.sections[domain]``.
        on_add_node:  Callback invoked on clicking a node; receives a
                      ``NodeDescriptor``.
    """
    # Groups by domain so each section can be sorted alphabetically.
    by_domain: dict[str, list[tuple[type, PaletteMeta]]] = {}

    for cls in _discover_palette_nodes():
        meta: PaletteMeta = cls.palette_meta()
        for domain in meta.domains:
            section_key = domain.capitalize()
            if section_key not in palette.sections:
                continue
            by_domain.setdefault(section_key, []).append((cls, meta))

    for section_key, entries in by_domain.items():
        entries.sort(key=lambda t: (t[1].name or t[0].__name__).lower())  # alphabetical order
        section = palette.sections[section_key]
        for cls, meta in entries:
            display_name = meta.name or cls.__name__
            # capturing variables via default arguments avoids the classic late-binding trap
            callback = lambda c=cls, d=section_key.lower(): on_add_node(NodeDescriptor(c, domain=d))
            item = section.add_node(
                name=display_name,
                icon_path=meta.sprite,
                callback=callback,
            )
            # route the click through NodePalette.select_item() too, so the
            # clicked item gets the blue "selected" outline while its node
            # is pending placement (ADD mode) -- add_node() alone only
            # wires the callback.
            palette.register_item(item, callback)
