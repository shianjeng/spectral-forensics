"""audit 与 reassign 的测试。

全部用 numpy 合成信号，不依赖 ffmpeg，也不需要任何音频素材。
"""

from pathlib import Path

import numpy as np
import pytest

from spectral_forensics.audit import find_cutoff, guess_source, long_term_spectrum
from spectral_forensics.io import Audio
from spectral_forensics.reassign import rasterize, reassign, sharpness
from spectral_forensics.transform import SpectroConfig

SR = 44100


def noise(dur: float = 4.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(int(SR * dur)).astype(np.float32) * 0.2


def brickwall(y: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """频域直接清零——模拟有损编码器的砖墙低通。"""
    Y = np.fft.rfft(y)
    f = np.fft.rfftfreq(len(y), d=1 / SR)
    Y[f > cutoff_hz] = 0.0
    return np.fft.irfft(Y, n=len(y)).astype(np.float32)


def chirp(f0: float, f1: float, dur: float = 3.0, sr: int = 22050) -> Audio:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    phase = 2 * np.pi * (f0 * t + 0.5 * (f1 - f0) / dur * t**2)
    return Audio(y=np.sin(phase).astype(np.float32), sr=sr, path=Path("chirp.wav"))


# ------------------------------------------------------------------ audit

def test_full_band_noise_has_no_cutoff():
    freqs, db = long_term_spectrum(noise(), SR)
    f_c, _ = find_cutoff(freqs, db)
    assert f_c is not None
    assert f_c > 0.95 * (SR / 2)      # 一路延伸到奈奎斯特


@pytest.mark.parametrize("cutoff", [12000.0, 16000.0, 19000.0])
def test_brickwall_cutoff_is_recovered(cutoff):
    """人工砖墙的位置应被找回，误差在 500 Hz 以内。"""
    freqs, db = long_term_spectrum(brickwall(noise(), cutoff), SR)
    f_c, steep = find_cutoff(freqs, db)
    assert f_c is not None
    assert abs(f_c - cutoff) < 500.0
    assert steep is not None and steep > 20.0   # 砖墙必然陡


def test_natural_rolloff_is_not_flagged_as_brickwall():
    """一阶低通的缓坡不该被当成编码器截止。"""
    y = noise()
    Y = np.fft.rfft(y)
    f = np.fft.rfftfreq(len(y), d=1 / SR)
    Y *= 1.0 / (1.0 + (f / 8000.0))        # 6 dB/oct 缓降
    y_soft = np.fft.irfft(Y, n=len(y)).astype(np.float32)

    freqs, db = long_term_spectrum(y_soft, SR)
    _, steep = find_cutoff(freqs, db)
    assert steep is None or steep < 20.0


def test_cutoff_to_bitrate_mapping():
    assert "128" in guess_source(16.0)
    assert "64" in guess_source(11.0)
    assert guess_source(3.0) == "未知有损编码"   # 离任何档位都太远


# --------------------------------------------------------------- reassign

def test_reassignment_sharpens_a_chirp():
    """同窗、同网格下，重分配后的能量必须更集中。"""
    audio = chirp(300.0, 4000.0)
    cfg = SpectroConfig(kind="stft", n_fft=2048, hop_length=256)

    base = rasterize(reassign(audio, cfg, enabled=False), n_time=600, n_freq=400)
    rea = rasterize(reassign(audio, cfg, enabled=True), n_time=600, n_freq=400)

    assert sharpness(rea) > sharpness(base)


def test_reassigned_tone_is_narrower_than_a_fft_bin():
    """纯音的重分配频率估计，散布应小于一个 FFT 频点宽度。

    这就是"突破不确定性下限"的具体含义：窗函数决定的 Δf 是 10.8 Hz，
    而重分配后的频率估计集中在远小于此的范围内。
    """
    f0 = 1000.0
    sr = 22050
    t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False)
    audio = Audio(y=np.sin(2 * np.pi * f0 * t).astype(np.float32),
                  sr=sr, path=Path("tone.wav"))
    cfg = SpectroConfig(kind="stft", n_fft=2048, hop_length=256)

    pts = reassign(audio, cfg, mag_top_db=40.0)
    near = pts.freqs[np.abs(pts.freqs - f0) < 200.0]
    assert near.size > 100

    spread = float(np.average(np.abs(near - f0),
                              weights=pts.weights[np.abs(pts.freqs - f0) < 200.0]))
    assert spread < cfg.freq_resolution(sr)      # < 10.8 Hz


def test_reassign_keeps_only_significant_points():
    audio = chirp(300.0, 4000.0)
    cfg = SpectroConfig(kind="stft", n_fft=1024, hop_length=256)
    loose = reassign(audio, cfg, mag_top_db=80.0)
    tight = reassign(audio, cfg, mag_top_db=30.0)
    assert len(tight) < len(loose)
