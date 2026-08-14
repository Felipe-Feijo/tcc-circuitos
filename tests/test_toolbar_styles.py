# tests/test_toolbar_styles.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

STYLES_PATH = Path(__file__).parent.parent / "resources" / "styles_dark.qss"


def test_toolbar_buttons_have_larger_padding_and_min_height():
    content = STYLES_PATH.read_text()
    assert "padding: 10px 16px;" in content
    assert "min-height: 28px;" in content
