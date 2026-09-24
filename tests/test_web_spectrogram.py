"""浏览器版时频图与 librosa / spectral_forensics 的一致性测试。

在线 Demo 的 STFT 和重分配谱是在 docs/analysis.js 里手写的。这里验证：
  - STFT 功率谱逐格等于 librosa.stft（center=True、零填充、周期 Hann）；
  - 重分配的时间、频率修正逐点等于 librosa.reassigned_spectrogram，保留的点集
    与 spf reassign 相同；
  - 栅格化结果与 spectral_forensics.reassign.rasterize 相同；
  - 重分配确实把纯音和脉冲收拢到真实位置（这是它存在的意义）。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import pytest

from spectral_forensics.io import Audio
from spectral_forensics.reassign import rasterize, reassign
from spectral_forensics.transform import SpectroConfig

RunJs = Callable[..., Any]  # conftest.run_js

SR = 22050
N_FFT = 1024
HOP = 256


def make_signal(seconds: float = 1.5) -> np.ndarray:
    """扫频 + 两个稳态音 + 两个脉冲 + 一点噪声，覆盖重分配的各种情况。"""
    t = np.arange(int(seconds * SR)) / SR
    y = 0.4 * np.sin(2 * np.pi * (300 * t + 0.5 * 2500 * t**2 / seconds))
    y += 0.2 * np.sin(2 * np.pi * 1234.5 * t) + 0.1 * np.sin(2 * np.pi * 5555.5 * t)
    for s in (0.37, 1.11):
        y[int(s * SR)] += 0.9
    y += 1e-3 * np.random.default_rng(0).standard_normal(len(t))
    return y


def test_stft_power_matches_librosa(run_js: RunJs):
    y = make_signal()
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP, pad_mode="constant")) ** 2
    ref_db = librosa.power_to_db(S, ref=np.max, top_db=80)

    js = run_js(
        f"const s = SPF.stftPower(y, {N_FFT}, {HOP});"
        " out({ nFrames: s.nFrames, nBins: s.nBins,"
        " db: Array.from(SPF.powerToDb(s.power, 80)) });",
        y=y,
    )
    assert (js["nBins"], js["nFrames"]) == S.shape
    js_db = np.array(js["db"]).reshape(js["nFrames"], js["nBins"]).T

    strong = ref_db > -60
    assert np.max(np.abs(js_db[strong] - ref_db[strong])) < 0.01
    # 裁剪区（-80 dB 地板）两边也必须一致
    assert np.mean(np.abs(js_db - ref_db) < 0.05) > 0.999


def test_reassigned_points_match_librosa(run_js: RunJs):
    y = make_signal()
    freqs, times, mags = librosa.reassigned_spectrogram(
        y=y, sr=SR, n_fft=N_FFT, hop_length=HOP, fill_nan=True, clip=True
    )
    db = librosa.power_to_db(mags**2, ref=np.max, top_db=None)
    keep = db > -60

    js = run_js(
        f"out(SPF.reassignedPoints(y, {SR}, {N_FFT}, {HOP}, 60));",
        y=y,
    )
    k = np.array(js["bins"], dtype=int)
    f = np.array(js["frames"], dtype=int)

    # 保留的格点集合与 spf reassign 相同
    js_keep = np.zeros_like(keep)
    js_keep[k, f] = True
    assert np.array_equal(js_keep, keep)

    np.testing.assert_allclose(js["freqs"], freqs[k, f], rtol=0, atol=1e-6)
    np.testing.assert_allclose(js["times"], times[k, f], rtol=0, atol=1e-9)
    np.testing.assert_allclose(js["weights"], mags[k, f] ** 2, rtol=1e-9)


@pytest.mark.parametrize("log_freq", [True, False])
def test_reassigned_raster_matches_rasterize(run_js: RunJs, log_freq: bool):
    y = make_signal()
    audio = Audio(y=y.astype(np.float32), sr=SR, path=Path("signal.wav"))
    pts = reassign(audio, SpectroConfig(kind="stft", n_fft=N_FFT, hop_length=HOP))
    ref = rasterize(pts, n_time=240, n_freq=160, fmin=40.0, log_freq=log_freq).S_db

    js = run_js(
        "const g = SPF.spectrogramRaster(y, "
        f"{SR}, {{nFft: {N_FFT}, hop: {HOP}, width: 240, height: 160, fmin: 40,"
        f" logFreq: {'true' if log_freq else 'false'}, mode: 'reassigned', topDb: 80}});"
        " let r; do { r = g.next(); } while (!r.done);"
        " out(Array.from(r.value.db));",
        y=audio.y.astype(np.float64),
    )
    js_db = np.array(js).reshape(160, 240)

    # 落在格子边界上的点可能分到相邻格，允许极少数像素不同
    close = np.abs(js_db - ref) < 0.1
    assert np.mean(close) > 0.995
    lit = ref > -40
    assert np.mean(close[lit]) > 0.99


def test_reassignment_pulls_tones_and_clicks_into_place(run_js: RunJs):
    """一个不在频点上的纯音、一个脉冲：STFT 各自糊成一片，重分配后收成一条线、一个点。"""
    t = np.arange(SR) / SR
    tone = 0.5 * np.sin(2 * np.pi * 1234.5 * t)
    click = np.zeros(SR)
    click[int(0.5 * SR)] = 1.0

    body = f"""
    const pts = y => SPF.reassignedPoints(y, {SR}, {N_FFT}, {HOP}, 30);
    const wstats = (v, w) => {{
      let sw = 0, m = 0;
      for (let i = 0; i < v.length; i++) {{ sw += w[i]; m += w[i] * v[i]; }}
      m /= sw;
      let s = 0;
      for (let i = 0; i < v.length; i++) s += w[i] * (v[i] - m) ** 2;
      return {{ mean: m, std: Math.sqrt(s / sw) }};
    }};
    const a = pts(tone), b = pts(click);
    // 纯音：只看离两端足够远、完整覆盖信号的帧
    const mid = a.frames.map((f, i) => f > 4 && f < a.frames.at(-1) - 4 ? i : -1)
                        .filter(i => i >= 0);
    out({{
      tone: wstats(mid.map(i => a.freqs[i]), mid.map(i => a.weights[i])),
      toneBins: new Set(mid.map(i => a.bins[i])).size,
      click: wstats(b.times, b.weights),
      clickFrames: new Set(b.frames).size,
    }});
    """
    js = run_js(body, tone=tone, click=click)

    bin_hz = SR / N_FFT  # 21.5 Hz
    # STFT 里纯音占好几个频点（窗的主瓣），重分配后全部收到 1234.5 Hz
    assert js["toneBins"] >= 3
    assert abs(js["tone"]["mean"] - 1234.5) < 0.05
    assert js["tone"]["std"] < 0.01 * bin_hz
    # 脉冲横跨好几帧，重分配后全部收到 0.5 s
    assert js["clickFrames"] >= 3
    assert abs(js["click"]["mean"] - 0.5) < 1 / SR
    assert js["click"]["std"] < 0.05 * HOP / SR
