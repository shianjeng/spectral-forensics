"""CLI 冒烟测试。

存在的理由很具体：`--help` 能通过不代表命令能跑。
argparse 的 help 根本不会碰到处理函数，所以一个被误删的
`def _run_audit(...)` 可以一路混过 `--help` 检查推上线，
直到真有人执行 audit 才炸。这里每个子命令都真跑一遍。
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from spectral_forensics.cli import main

SR = 22050


@pytest.fixture(scope="module")
def track(tmp_path_factory) -> Path:
    """一段短音频：正弦 + 噪声，够所有命令跑通。"""
    d = tmp_path_factory.mktemp("audio")
    p = d / "track.wav"
    t = np.linspace(0, 2.0, int(SR * 2.0), endpoint=False)
    rng = np.random.default_rng(0)
    y = (
        0.5 * np.sin(2 * np.pi * 440 * t)
        + 0.2 * np.sin(2 * np.pi * 1800 * t)
        + 0.02 * rng.standard_normal(len(t))
    )
    sf.write(p, y.astype(np.float32), SR)
    return p


@pytest.fixture(scope="module")
def picture(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("img")
    p = d / "pic.png"
    a = np.linspace(0, 255, 96 * 96).reshape(96, 96).astype(np.uint8)
    Image.fromarray(a).save(p)
    return p


def test_poster(track, tmp_path):
    out = tmp_path / "poster.png"
    assert main(["poster", str(track), "-o", str(out)]) == 0
    assert out.exists()


def test_compare(track, tmp_path):
    out = tmp_path / "cmp.png"
    assert main(["compare", str(track), "-o", str(out), "--n-ffts", "512,2048"]) == 0
    assert out.exists()


def test_reassign(track, tmp_path):
    out = tmp_path / "rea.png"
    assert main(["reassign", str(track), "-o", str(out), "--grid", "200x150"]) == 0
    assert out.exists()


def test_edit(track, tmp_path):
    out = tmp_path / "edited.wav"
    assert main(["edit", str(track), "--reject", "1000:2000", "-o", str(out)]) == 0
    assert out.exists()


def test_edit_without_any_operation_fails(track, tmp_path):
    """没给任何编辑动作时应当报错退出，而不是默默写一个原样的文件。"""
    assert main(["edit", str(track), "-o", str(tmp_path / "x.wav")]) == 1


def test_sonify(picture, tmp_path):
    out = tmp_path / "sonified.wav"
    assert (
        main(
            ["sonify", str(picture), "-o", str(out), "--frames", "120", "--iters", "4"]
        )
        == 0
    )
    assert out.exists()


def test_audit_single_file(track):
    assert main(["audit", str(track)]) == 0


def test_audit_directory_json(track):
    assert main(["audit", str(track.parent), "-r", "--json"]) == 0


def test_check_reports_environment():
    assert main(["check"]) == 0
    assert main(["check", "--json"]) == 0


def test_video_missing_ffmpeg_returns_clear_error(track, monkeypatch, capsys):
    monkeypatch.setattr("spectral_forensics.video.ffmpeg_available", lambda: False)
    out = track.parent / "x.mp4"
    assert main(["video", str(track), "-o", str(out)]) == 1
    err = capsys.readouterr().err
    assert "未找到 ffmpeg" in err
    assert "video" in err
    assert "mp3/m4a" in err


def test_video_minimal_run_when_ffmpeg_available(track, tmp_path):
    import shutil

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    out = tmp_path / "video.mp4"
    assert (
        main(
            [
                "video",
                str(track),
                "-o",
                str(out),
                "--fps",
                "5",
                "--size",
                "320x180",
                "--bars",
                "24",
            ]
        )
        == 0
    )
    assert out.exists()
