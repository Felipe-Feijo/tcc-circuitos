"""Preferências de UI persistidas: tamanho de fonte e tier de tamanho da paleta."""

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QInputDialog

DEFAULT_FONT_SIZE = 11
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 20

DEFAULT_PALETTE_TIER = "medium"

_FONT_SIZE_KEY = "ui/font_point_size"
_PALETTE_TIER_KEY = "ui/palette_size_tier"


def _default_settings() -> QSettings:
    return QSettings("tcc-circuitos", "CircuitEditor")


def get_font_size(settings: QSettings | None = None) -> int:
    s = settings or _default_settings()
    try:
        size = int(s.value(_FONT_SIZE_KEY, DEFAULT_FONT_SIZE))
    except (TypeError, ValueError):
        return DEFAULT_FONT_SIZE
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))


def set_font_size(pt: int, settings: QSettings | None = None) -> None:
    s = settings or _default_settings()
    s.setValue(_FONT_SIZE_KEY, pt)


def get_palette_tier(settings: QSettings | None = None) -> str:
    s = settings or _default_settings()
    return str(s.value(_PALETTE_TIER_KEY, DEFAULT_PALETTE_TIER))


def set_palette_tier(tier: str, settings: QSettings | None = None) -> None:
    s = settings or _default_settings()
    s.setValue(_PALETTE_TIER_KEY, tier)


def apply_font_from_settings(app: QApplication, settings: QSettings | None = None) -> None:
    size = get_font_size(settings)
    font = app.font()
    font.setPointSize(size)
    app.setFont(font)


def prompt_and_apply_font_size(parent, settings: QSettings | None = None) -> bool:
    """Abre um diálogo pedindo o tamanho de fonte (pt); aplica e persiste
    se o usuário confirmar. Retorna True se algo foi alterado."""
    current = get_font_size(settings)
    value, ok = QInputDialog.getInt(
        parent, "Font Size", "Point size:", current, MIN_FONT_SIZE, MAX_FONT_SIZE
    )
    if not ok:
        return False

    app = QApplication.instance()
    font = app.font()
    font.setPointSize(value)
    app.setFont(font)
    set_font_size(value, settings)
    return True
