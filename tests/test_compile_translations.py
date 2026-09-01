import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from scripts.compile_translations import compile_all

_SAMPLE_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="pt_BR">
<context>
    <name>Sample</name>
    <message>
        <source>Hello</source>
        <translation>Olá</translation>
    </message>
</context>
</TS>
"""


def test_compile_all_produces_one_qm_per_ts():
    with tempfile.TemporaryDirectory() as tmp:
        i18n_dir = Path(tmp)
        (i18n_dir / "sample_pt_BR.ts").write_text(_SAMPLE_TS, encoding="utf-8")

        produced = compile_all(i18n_dir)

        assert produced == [i18n_dir / "sample_pt_BR.qm"]
        assert (i18n_dir / "sample_pt_BR.qm").exists()
        assert (i18n_dir / "sample_pt_BR.qm").stat().st_size > 0
