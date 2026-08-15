import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image

from simulation.report.report_builder import build_video


def _make_png(path, color):
    Image.new("RGB", (64, 48), color=color).save(path)


def test_build_video_creates_mp4_file(tmp_path):
    paths = []
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        p = tmp_path / f"frame_{i}.png"
        _make_png(p, color)
        paths.append(str(p))

    out = tmp_path / "video.mp4"
    ok = build_video(paths, str(out), fps=5)

    assert ok is True
    assert out.exists()
    assert out.stat().st_size > 0


def test_build_video_returns_false_for_empty_frame_list(tmp_path):
    out = tmp_path / "video.mp4"
    ok = build_video([], str(out))

    assert ok is False
    assert not out.exists()


def test_build_video_returns_false_on_encoder_failure(tmp_path, monkeypatch):
    import simulation.report.report_builder as rb

    def _boom(*args, **kwargs):
        raise RuntimeError("encoder indisponível")

    monkeypatch.setattr(rb.imageio, "get_writer", _boom)

    out = tmp_path / "video.mp4"
    ok = build_video(["nao_importa.png"], str(out))

    assert ok is False
