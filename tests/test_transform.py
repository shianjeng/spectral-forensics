"""核心变换的单元测试。用合成正弦波，不依赖任何音频素材。"""

from pathlib import Path

import numpy as np
import pytest

from sonogram.io import Audio
from sonogram.transform import SpectroConfig, compute, frame_spectrum


def sine(freq: float, sr: int = 22050, dur: float = 2.0) -> Audio:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return Audio(y=np.sin(2 * np.pi * freq * t).astype(np.float32),
                 sr=sr, path=Path("sine.wav"))


def test_uncertainty_product_is_unity():
    """Δt · Δf = 1，与 n_fft 无关——这是整个项目的物理主张。"""
    sr = 22050
    for n_fft in (512, 2048, 8192):
        cfg = SpectroConfig(n_fft=n_fft)
        assert cfg.time_resolution(sr) * cfg.freq_resolution(sr) == pytest.approx(1.0)


def test_stft_peak_lands_on_input_frequency():
    """1000 Hz 正弦波的谱峰应落在 1000 Hz 附近，误差不超过一个频点。"""
    f0 = 1000.0
    audio = sine(f0)
    cfg = SpectroConfig(kind="stft", n_fft=2048)
    spec = compute(audio, cfg)

    mid = spec.S_db[:, spec.S_db.shape[1] // 2]
    peak_hz = spec.freqs[int(np.argmax(mid))]
    assert abs(peak_hz - f0) <= cfg.freq_resolution(audio.sr)


def test_finer_n_fft_gives_finer_frequency_resolution():
    sr = 22050
    assert (SpectroConfig(n_fft=8192).freq_resolution(sr)
            < SpectroConfig(n_fft=512).freq_resolution(sr))


@pytest.mark.parametrize("kind", ["stft", "mel", "cqt"])
def test_all_transforms_produce_sane_matrices(kind):
    spec = compute(sine(440.0), SpectroConfig(kind=kind, n_fft=2048))
    assert spec.S_db.ndim == 2
    assert spec.S_db.shape[0] == len(spec.freqs)
    assert spec.S_db.shape[1] == len(spec.times)
    assert np.isfinite(spec.S_db).all()


def test_top_db_clips_dynamic_range():
    """转 dB 后动态范围不应超过 top_db。"""
    spec = compute(sine(440.0), SpectroConfig(kind="stft", top_db=60.0))
    assert spec.S_db.max() - spec.S_db.min() <= 60.0 + 1e-6


def test_frame_spectrum_is_clamped_at_both_ends():
    spec = compute(sine(440.0, dur=1.0))
    assert frame_spectrum(spec, -5.0).shape == (spec.S_db.shape[0],)
    assert frame_spectrum(spec, 999.0).shape == (spec.S_db.shape[0],)
