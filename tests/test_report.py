"""HTML 报告的测试。

报告是要发给别人看的，所以两件事必须守住：文件名和路径来自磁盘，
必须转义；以及一个画不出缩略图的坏文件不能让整份报告失败。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from spectral_forensics.audit import AuditResult, audit_path
from spectral_forensics.report import build_report, write_report

SR = 44100


def fake_result(**kw) -> AuditResult:
    base = {
        "path": "/music/track.flac",
        "verdict": "suspect",
        "confidence": 0.9,
        "cutoff_khz": 16.0,
        "nyquist_khz": 22.05,
        "steepness_db": 74.0,
        "stereo_cutoff_khz": None,
        "codec": "flac",
        "declared_kbps": None,
        "guess": "mp3 ~128 kbps",
        "notes": ["砖墙特征"],
    }
    base.update(kw)
    return AuditResult(**base)


def test_report_lists_every_file_and_counts_the_tiers():
    results = [
        fake_result(path="/m/a.flac", verdict="suspect"),
        fake_result(path="/m/b.flac", verdict="likely", confidence=0.5),
        fake_result(path="/m/c.flac", verdict="clean", confidence=0.0),
    ]
    html = build_report(results, "/m", thumbnails=False)

    for name in ("a.flac", "b.flac", "c.flac"):
        assert name in html
    assert "1 suspect" in html
    assert "1 likely" in html
    assert "1 clean" in html


def test_suspect_files_are_listed_before_clean_ones():
    """报告是拿来找问题的，可疑的必须排在最前面。"""
    results = [
        fake_result(path="/m/zz-clean.flac", verdict="clean"),
        fake_result(path="/m/aa-suspect.flac", verdict="suspect"),
    ]
    html = build_report(results, "/m", thumbnails=False)
    assert html.index("aa-suspect.flac") < html.index("zz-clean.flac")


def test_filenames_are_escaped():
    """文件名来自磁盘，可以包含任何字符，绝不能直接拼进 HTML。"""
    html = build_report(
        [fake_result(path="/m/<script>alert(1)</script>.flac")], "/m", thumbnails=False
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_notes_are_escaped_too():
    html = build_report(
        [fake_result(notes=["<img onerror=x>"])], "/m", thumbnails=False
    )
    assert "<img onerror=x>" not in html
    assert "&lt;img" in html


def test_a_missing_file_does_not_break_the_report():
    """缩略图画不出来时，条目照常列出，只是没有图。"""
    html = build_report(
        [fake_result(path="/does/not/exist.flac")], "/does", thumbnails=True
    )
    assert "exist.flac" in html
    assert "no spectrum" in html


def test_end_to_end_report_embeds_a_thumbnail(tmp_path: Path):
    """真跑一遍：造一个有 16 kHz 砖墙的文件，报告里应当嵌着它的谱图。"""
    rng = np.random.default_rng(0)
    y = rng.standard_normal(SR * 3).astype(np.float32) * 0.2
    Y = np.fft.rfft(y)
    f = np.fft.rfftfreq(len(y), d=1 / SR)
    Y[f > 16000] = 0.0
    y = np.fft.irfft(Y, n=len(y)).astype(np.float32)
    sf.write(tmp_path / "fake.flac", y, SR)

    results = audit_path(tmp_path, recursive=False)
    assert results and results[0].verdict == "suspect"

    out = write_report(results, tmp_path / "report.html", tmp_path)
    html = out.read_text(encoding="utf-8")
    assert "data:image/png;base64," in html
    assert "fake.flac" in html


@pytest.mark.parametrize("verdict", ["suspect", "likely", "lossy", "clean", "unknown"])
def test_every_verdict_renders(verdict):
    html = build_report([fake_result(verdict=verdict)], "/m", thumbnails=False)
    assert "<article" in html
