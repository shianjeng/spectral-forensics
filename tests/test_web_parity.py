"""浏览器版与 Python 版的一致性测试。

`docs/index.html` 里内联了一份 JavaScript 的转码检测实现。README 宣称它
"checked against the Python implementation on identical signals"——这条测试
就是那句话的依据：同样的信号喂给两边，截止频率必须落在同一个 FFT 频点上。

没装 node 时跳过（本地开发不强制），CI 的 ubuntu runner 自带 node。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from spectral_forensics.audit import find_cutoff, long_term_spectrum

SR = 44100
PAGE = Path(__file__).resolve().parent.parent / "docs" / "index.html"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")


def brickwall(y: np.ndarray, cutoff_hz: float | None) -> np.ndarray:
    if cutoff_hz is None:
        return y
    Y = np.fft.rfft(y)
    f = np.fft.rfftfreq(len(y), d=1 / SR)
    Y[f > cutoff_hz] = 0.0
    return np.fft.irfft(Y, n=len(y)).astype(np.float32)


def extract_js() -> str:
    """把页面里的算法部分抠出来，去掉依赖 DOM 的代码。"""
    html = PAGE.read_text(encoding="utf-8")
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert script, "docs/index.html 里找不到 <script> 块"
    return script.group(1).split("/* ---------------------------- 绘图")[0]


def test_page_exists_and_has_the_algorithm():
    assert PAGE.exists(), "缺少 docs/index.html"
    js = extract_js()
    for fn in ("longTermSpectrum", "findCutoff", "verdict", "FULL_BAND_KHZ"):
        assert fn in js, f"页面里缺少 {fn}"


@pytest.mark.parametrize("cutoff", [13000.0, 16000.0, 19000.0, None])
def test_js_and_python_agree_on_the_cutoff(cutoff):
    rng = np.random.default_rng(1)
    y = brickwall(rng.standard_normal(SR * 3).astype(np.float32) * 0.2, cutoff)

    freqs, db = long_term_spectrum(y, SR)
    py_fc, _ = find_cutoff(freqs, db)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "core.mjs").write_text(
            extract_js() + "\nexport {longTermSpectrum, findCutoff};\n",
            encoding="utf-8")
        (tmp / "sig.f32").write_bytes(y.tobytes())
        (tmp / "run.mjs").write_text(f"""
import fs from "fs";
import {{ longTermSpectrum, findCutoff }} from "{tmp / 'core.mjs'}";
const b = fs.readFileSync("{tmp / 'sig.f32'}");
const y = new Float32Array(b.buffer, b.byteOffset, b.length / 4);
const {{ freqs, db }} = longTermSpectrum(y, {SR});
const c = findCutoff(freqs, db);
console.log(JSON.stringify({{ cutoffHz: c.cutoffHz }}));
""", encoding="utf-8")

        out = subprocess.run(["node", str(tmp / "run.mjs")],
                             capture_output=True, text=True,
                             timeout=180, check=False)
        assert out.returncode == 0, out.stderr
        js_fc = json.loads(out.stdout)["cutoffHz"]

    assert py_fc is not None and js_fc is not None
    # 一个 FFT 频点 = sr/n_fft ≈ 5.4 Hz，两边必须落在同一格
    assert abs(js_fc - py_fc) < SR / 8192
