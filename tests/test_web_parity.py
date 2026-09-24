"""浏览器版与 Python 版的一致性测试：转码检测。

`docs/analysis.js` 是在线 Demo 用的 JavaScript 实现。README 宣称它
"checked against the Python implementation on identical signals"——这些测试
就是那句话的依据：同样的信号喂给两边，截止频率必须落在同一个 FFT 频点上，
示例音频的判定也必须一致。
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from spectral_forensics.audit import audit_file, find_cutoff, long_term_spectrum

RunJs = Callable[..., Any]  # conftest.run_js

SR = 44100
DOCS = Path(__file__).resolve().parent.parent / "docs"
PAGE = DOCS / "index.html"
SAMPLES = DOCS / "samples"

# 页面对一个文件做的事：前 120 s，单声道求截止，双声道看边信号，再下结论
VERDICT_JS = """
const n = Math.min(L.length, 120 * SR);
const l = L.subarray(0, n), r = R.subarray(0, n);
const mono = new Float64Array(n);
for (let i = 0; i < n; i++) mono[i] = (l[i] + r[i]) / 2;
const { freqs, db } = SPF.longTermSpectrum(mono, SR);
const cut = SPF.findCutoff(freqs, db);
const stereoHz = SPF.intensityStereoCutoff(l, r, SR);
const v = SPF.verdict(cut, stereoHz, true);
out({ tier: v.tier, cutoffHz: cut.cutoffHz, notes: v.notes.map(x => x.code) });
"""


def brickwall(y: np.ndarray, cutoff_hz: float | None) -> np.ndarray:
    if cutoff_hz is None:
        return y
    Y = np.fft.rfft(y)
    f = np.fft.rfftfreq(len(y), d=1 / SR)
    Y[f > cutoff_hz] = 0.0
    return np.fft.irfft(Y, n=len(y)).astype(np.float32)


def test_page_loads_the_scripts():
    html = PAGE.read_text(encoding="utf-8")
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts[:1] == ["analysis.js"], "analysis.js 必须最先加载"
    for src in scripts:
        assert (DOCS / src).exists(), f"页面引用了不存在的 {src}"
    for name in ("demo-genuine.flac", "demo-128k.mp3"):
        assert (SAMPLES / name).exists(), f"缺少示例音频 {name}"


@pytest.mark.parametrize("cutoff", [13000.0, 16000.0, 19000.0, None])
def test_js_and_python_agree_on_the_cutoff(run_js: RunJs, cutoff):
    rng = np.random.default_rng(1)
    y = brickwall(rng.standard_normal(SR * 3).astype(np.float32) * 0.2, cutoff)

    freqs, db = long_term_spectrum(y, SR)
    py_fc, _ = find_cutoff(freqs, db)

    js = run_js(
        f"const {{ freqs, db }} = SPF.longTermSpectrum(Float32Array.from(y), {SR});"
        " out({ cutoffHz: SPF.findCutoff(freqs, db).cutoffHz });",
        y=y,
    )
    js_fc = js["cutoffHz"]

    assert py_fc is not None and js_fc is not None
    # 一个 FFT 频点 = sr/n_fft ≈ 5.4 Hz，两边必须落在同一格
    assert abs(js_fc - py_fc) < SR / 8192


def _as_flac(path: Path, tmp_path: Path) -> Path:
    """mp3 → FLAC：页面把 mp3 示例当成"转回无损的 mp3"来分析，Python 这边照做。"""
    if path.suffix == ".flac":
        return path
    y, sr = sf.read(path, dtype="float32")
    dst = tmp_path / (path.stem + ".flac")
    sf.write(dst, y, sr, subtype="PCM_16")
    return dst


@pytest.mark.parametrize(
    ("name", "tier"),
    [("demo-genuine.flac", "clean"), ("demo-128k.mp3", "suspect")],
)
def test_sample_verdicts_match(run_js: RunJs, tmp_path: Path, name: str, tier: str):
    path = SAMPLES / name
    py = audit_file(_as_flac(path, tmp_path))
    assert py.verdict == tier, py.notes

    y, sr = sf.read(path, dtype="float32", always_2d=True)
    assert sr == SR and y.shape[1] == 2
    js = run_js(f"const SR = {SR};" + VERDICT_JS, L=y[:, 0], R=y[:, 1])
    assert js["tier"] == tier, js
    assert py.cutoff_khz is not None and js["cutoffHz"] is not None
    assert abs(js["cutoffHz"] / 1000 - py.cutoff_khz) < 0.1


def test_the_js_file_is_valid_for_node(node: str):
    """analysis.js 与 app.js 至少要能被解析（CI 里另有一步 node --check）。"""
    for js in ("analysis.js", "i18n.js", "app.js"):
        proc = subprocess.run(
            [node, "--check", str(DOCS / js)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr


def test_every_language_covers_every_string(run_js: RunJs):
    """英中日三种语言的键必须一致，页面上每个 data-i18n 键都要有翻译。"""
    html = PAGE.read_text(encoding="utf-8")
    used = set(re.findall(r'data-i18n(?:-html)?="([^"]+)"', html))
    keys = run_js(
        f"const I = require({str(DOCS / 'i18n.js')!r});"
        " out(Object.fromEntries(Object.entries(I).map(([k, v]) => [k, Object.keys(v)])));"
    )
    assert set(keys) == {"en", "zh", "ja"}
    for lang in ("zh", "ja"):
        assert set(keys[lang]) == set(keys["en"]), lang
    assert used, "页面里没有 data-i18n"
    missing = used - set(keys["en"])
    assert not missing, f"i18n.js 缺少 {sorted(missing)}"
