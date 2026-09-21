"""可逆编辑的测试：重建精度、掩码效果、Griffin-Lim 收敛。"""

from pathlib import Path

import librosa
import numpy as np
import pytest

from sonogram.io import Audio
from sonogram.invert import (analyze, apply_mask, band_mask, image_to_magnitude,
                             spectral_convergence, spectral_gate, synthesize)
from sonogram.transform import SpectroConfig

SR = 22050
CFG = SpectroConfig(kind="stft", n_fft=2048, hop_length=512)


def mixture(dur: float = 3.0) -> Audio:
    """三个正弦的叠加，分别落在低、中、高频，方便检验频段操作。"""
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    y = (np.sin(2 * np.pi * 300 * t)
         + np.sin(2 * np.pi * 3000 * t)
         + np.sin(2 * np.pi * 7000 * t)) / 3.0
    return Audio(y=y.astype(np.float32), sr=SR, path=Path("mix.wav"))


def band_energy(y: np.ndarray, lo: float, hi: float) -> float:
    D = np.abs(librosa.stft(y, n_fft=2048))
    f = librosa.fft_frequencies(sr=SR, n_fft=2048)
    return float((D[(f >= lo) & (f <= hi)] ** 2).sum())


def test_identity_roundtrip_is_numerically_exact():
    """恒等掩码下 STFT→ISTFT 必须几乎完全还原——这是"可逆"的定义。"""
    audio = mixture()
    spec = analyze(audio, CFG)
    y = apply_mask(spec, np.ones_like(spec.magnitude), length=len(audio.y))

    rel = np.linalg.norm(y - audio.y) / np.linalg.norm(audio.y)
    assert rel < 1e-6           # 实测约 1e-8，即 −158 dB


def test_band_reject_removes_only_the_target_band():
    audio = mixture()
    spec = analyze(audio, CFG)
    y = apply_mask(spec, band_mask(spec, 2500, 3500, keep=False),
                   length=len(audio.y))

    removed = band_energy(y, 2900, 3100) / band_energy(audio.y, 2900, 3100)
    kept_lo = band_energy(y, 250, 350) / band_energy(audio.y, 250, 350)
    kept_hi = band_energy(y, 6900, 7100) / band_energy(audio.y, 6900, 7100)

    assert removed < 1e-3       # 目标频段掉 30 dB 以上
    assert kept_lo > 0.95       # 其余频段基本不动
    assert kept_hi > 0.95


def test_band_keep_is_the_complement():
    audio = mixture()
    spec = analyze(audio, CFG)
    y = apply_mask(spec, band_mask(spec, 2500, 3500, keep=True),
                   length=len(audio.y))

    assert band_energy(y, 2900, 3100) / band_energy(audio.y, 2900, 3100) > 0.95
    assert band_energy(y, 250, 350) / band_energy(audio.y, 250, 350) < 1e-3


def gated_notes(dur: float = 4.0) -> Audio:
    """断续的音符——每个频点都有安静的时候，满足最小统计法的前提。"""
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    y = np.zeros_like(t)
    for k, f in enumerate((300.0, 3000.0, 7000.0)):
        on = ((t + k * 0.4) % 1.2) < 0.5
        y += np.sin(2 * np.pi * f * t) * on
    return Audio(y=(y / 3.0).astype(np.float32), sr=SR, path=Path("notes.wav"))


def test_denoise_improves_snr_on_a_noisy_signal():
    """低信噪比时谱减应当提升 SNR。

    两个前提，缺一不可：
    1. 噪声要明显——信噪比本来就高的素材，门限带来的失真会超过它去掉的噪声
       （见 README 的实测表，17 dB 输入反而掉 0.2 dB）。
    2. 信号要非平稳——最小统计法假设每个频点总有安静下来的时候。
       一个从头响到尾的稳态纯音会把自己估成噪声，然后被自己的门限砍掉。
    """
    audio = gated_notes()
    rng = np.random.default_rng(0)
    noisy = audio.y + rng.standard_normal(len(audio.y)).astype(np.float32) * 0.25

    def snr(x):
        n = min(len(audio.y), len(x))
        err = x[:n] - audio.y[:n]
        return 10 * np.log10((audio.y[:n] ** 2).sum() / ((err ** 2).sum() + 1e-20))

    spec = analyze(Audio(y=noisy.astype(np.float32), sr=SR,
                         path=Path("noisy.wav")), CFG)
    cleaned = apply_mask(spec, spectral_gate(spec), length=len(audio.y))

    assert snr(cleaned) > snr(noisy)


def test_griffin_lim_converges_with_more_iterations():
    """迭代越多，谱收敛误差应当单调下降（或至少不上升）。"""
    audio = mixture(dur=1.5)
    target = np.abs(librosa.stft(audio.y, n_fft=CFG.n_fft,
                                 hop_length=CFG.hop_length))

    errs = [spectral_convergence(target, synthesize(target, SR, CFG, n_iter=n), CFG)
            for n in (1, 8, 48)]
    assert errs[0] > errs[1] > errs[2]
    assert errs[-1] < 0.25


def test_image_to_magnitude_stays_inside_the_requested_band(tmp_path):
    """照片编码出的能量必须全部落在 [fmin, fmax] 内。"""
    from PIL import Image

    img = tmp_path / "grad.png"
    Image.fromarray((np.linspace(0, 255, 64 * 64)
                     .reshape(64, 64)).astype(np.uint8)).save(img)

    mag = image_to_magnitude(img, SR, CFG, n_frames=100,
                             fmin=500.0, fmax=4000.0)
    freqs = librosa.fft_frequencies(sr=SR, n_fft=CFG.n_fft)
    outside = mag[(freqs < 500.0) | (freqs > 4000.0)]
    assert np.allclose(outside, 0.0)
    assert mag.max() > 0


@pytest.mark.parametrize("keep", [True, False])
def test_band_mask_values_stay_in_range(keep):
    spec = analyze(mixture(dur=1.0), CFG)
    m = band_mask(spec, 1000, 2000, keep=keep)
    assert m.min() >= 0.0 and m.max() <= 1.0


def test_griffinlim_seed_kwarg_matches_installed_librosa():
    """播种参数名必须真的存在于当前 librosa 的签名里。

    这条测试是 CI 抓出 bug 后补的：代码原本写死了 librosa 1.0 的 `rng`，
    而 pyproject 声明的下限是 0.10，那里这个参数叫 `random_state`。
    装到旧版的用户会直接撞 TypeError。
    """
    import inspect as _inspect

    from sonogram.invert import _griffinlim_seed_kwarg

    name = _griffinlim_seed_kwarg()
    if name:
        assert name in _inspect.signature(librosa.griffinlim).parameters
