"""可逆编辑：在频域动手脚，再变回声音。

到这一步，谱图不再是渲染的终点，而是一种可编辑的媒介。

两条重建路径，用途完全不同：

1. **保相位重建**（`apply_mask`）
   只改幅度、原样保留相位，然后直接逆 STFT。掩码运算（降噪、去某个频段、
   隔离某件乐器）都走这条路——因为原始相位仍然和保留下来的幅度自洽，
   重建几乎无损。恒等掩码下误差在数值精度量级。

2. **Griffin-Lim 相位重建**（`synthesize`）
   幅度是凭空造出来的（比如把一张照片当成频谱），根本没有对应的相位。
   Griffin-Lim 反复在"时域信号"和"给定幅度"两个集合之间投影，逼出一组
   自洽的相位。它只保证收敛到局部解，所以听感会有金属味，这是原理决定的，
   不是实现的 bug。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from .io import Audio
from .transform import SpectroConfig


@dataclass(frozen=True)
class ComplexSpec:
    """保留相位的复数 STFT，编辑流程的中间表示。"""

    D: np.ndarray            # 复数，(n_freq, n_frames)
    sr: int
    config: SpectroConfig

    @property
    def magnitude(self) -> np.ndarray:
        return np.abs(self.D)

    @property
    def phase(self) -> np.ndarray:
        return np.exp(1j * np.angle(self.D))

    @property
    def freqs(self) -> np.ndarray:
        return librosa.fft_frequencies(sr=self.sr, n_fft=self.config.n_fft)

    @property
    def times(self) -> np.ndarray:
        return librosa.frames_to_time(np.arange(self.D.shape[1]), sr=self.sr,
                                      hop_length=self.config.hop_length)


def analyze(audio: Audio, config: SpectroConfig | None = None) -> ComplexSpec:
    """音频 → 复数 STFT。"""
    cfg = config or SpectroConfig(kind="stft")
    D = librosa.stft(audio.y, n_fft=cfg.n_fft, hop_length=cfg.hop_length,
                     window=cfg.window)
    return ComplexSpec(D=D, sr=audio.sr, config=cfg)


# ------------------------------------------------------------ 保相位重建

def apply_mask(spec: ComplexSpec, mask: np.ndarray,
               length: int | None = None) -> np.ndarray:
    """按掩码缩放幅度、保留原相位，逆 STFT 回到波形。

    mask 取值 [0, 1]，形状需与 spec.D 一致（或可广播）。
    """
    mask = np.asarray(mask, dtype=np.float64)
    if mask.shape != spec.D.shape:
        mask = np.broadcast_to(mask, spec.D.shape)

    D_edited = spec.D * mask
    return librosa.istft(D_edited, hop_length=spec.config.hop_length,
                         win_length=spec.config.n_fft,
                         window=spec.config.window, length=length)


def band_mask(spec: ComplexSpec, lo_hz: float, hi_hz: float,
              keep: bool = False, taper_hz: float = 50.0) -> np.ndarray:
    """频段掩码。keep=False 表示剔除该频段，True 表示只保留该频段。

    边缘做余弦过渡，避免砖墙滤波带来的时域振铃。
    """
    f = spec.freqs
    band = np.ones_like(f)

    if taper_hz > 0:
        band = np.clip((f - (lo_hz - taper_hz)) / taper_hz, 0, 1) * \
               np.clip(((hi_hz + taper_hz) - f) / taper_hz, 0, 1)
        band = np.clip(band, 0, 1)
    else:
        band = ((f >= lo_hz) & (f <= hi_hz)).astype(float)

    if not keep:
        band = 1.0 - band
    return band[:, None]


def spectral_gate(spec: ComplexSpec, reduction_db: float = 12.0,
                  threshold_db: float = 8.0,
                  noise_percentile: float = 15.0,
                  noise_frames: tuple[int, int] | None = None) -> np.ndarray:
    """谱减降噪掩码。

    噪声本底默认用**最小统计法**估计：对每个频点，取它在整条时间轴上的低分位数。
    直觉是任何一个频点总有安静下来的时候，那时剩下的就是本底噪声。
    这比"拿开头几帧当噪声样本"稳健得多——一开头就有声音的素材，
    用前者会把噪声估过头，掩码于是连真信号一起砍掉。

    前提：信号是非平稳的——每个频点总有安静下来的时候。一个从头响到尾的
    稳态纯音会把自己估成噪声本底，然后被自己的门限砍掉。这类素材请改用
    noise_frames=(a, b) 指定一段确知的纯噪声区间。
    """
    mag = spec.magnitude

    if noise_frames is not None:
        a, b = noise_frames
        noise = np.percentile(mag[:, a:b], 75, axis=1, keepdims=True)
    else:
        noise = np.percentile(mag, noise_percentile, axis=1, keepdims=True)

    thresh = noise * (10 ** (threshold_db / 20.0))
    gain_floor = 10 ** (-reduction_db / 20.0)
    mask = np.where(mag > thresh, 1.0, gain_floor)

    # 时频两个方向各做一点平滑，否则会有"音乐噪声"（鸟鸣般的伪影）
    k = np.ones((3, 3)) / 9.0
    pad = np.pad(mask, 1, mode="edge")
    smooth = sum(k[i, j] * pad[i:i + mask.shape[0], j:j + mask.shape[1]]
                 for i in range(3) for j in range(3))
    return smooth


def mask_from_image(path: str | Path, shape: tuple[int, int],
                    invert: bool = False) -> np.ndarray:
    """把一张灰度图当掩码用——等于在任意画图软件里"涂抹"频谱。

    图像会被缩放到 (n_freq, n_frames)，且上下翻转，
    使图片顶部对应高频、符合看谱图的直觉。
    """
    from PIL import Image

    img = Image.open(path).convert("L").resize((shape[1], shape[0]),
                                               Image.LANCZOS)
    m = np.asarray(img, dtype=np.float64) / 255.0
    m = m[::-1]                       # 图像行序是从上往下，谱图是从下往上
    return 1.0 - m if invert else m


# ------------------------------------------------- Griffin-Lim 无相位重建

def _griffinlim_seed_kwarg() -> str:
    """librosa 0.x 用 random_state 给 Griffin-Lim 播种，1.0 改叫 rng。

    pyproject 声明的下限是 librosa>=0.10，所以两种都得支持——
    写死其中一个会让另一半用户直接崩在 TypeError 上。
    """
    params = inspect.signature(librosa.griffinlim).parameters
    if "rng" in params:
        return "rng"
    if "random_state" in params:
        return "random_state"
    return ""          # 更老的版本不支持播种，只好让它随机


def synthesize(magnitude: np.ndarray, sr: int,
               config: SpectroConfig | None = None,
               n_iter: int = 64, momentum: float = 0.99,
               seed: int = 0) -> np.ndarray:
    """从纯幅度谱重建波形（无原始相位可用时）。"""
    cfg = config or SpectroConfig(kind="stft")

    kwargs = dict(
        n_iter=n_iter, hop_length=cfg.hop_length, win_length=cfg.n_fft,
        n_fft=cfg.n_fft, window=cfg.window,
        momentum=momentum, init="random",
    )
    seed_kwarg = _griffinlim_seed_kwarg()
    if seed_kwarg:
        kwargs[seed_kwarg] = seed

    return librosa.griffinlim(
        np.asarray(magnitude, dtype=np.float64), **kwargs)


def spectral_convergence(target_mag: np.ndarray, y: np.ndarray,
                         config: SpectroConfig) -> float:
    """重建质量指标：‖|STFT(y)| − target‖ / ‖target‖，越小越好。

    用它可以定量说明 Griffin-Lim 迭代确实在收敛，而不是靠耳朵判断。
    """
    D = librosa.stft(y, n_fft=config.n_fft, hop_length=config.hop_length,
                     window=config.window)
    mag = np.abs(D)
    n = min(mag.shape[1], target_mag.shape[1])
    diff = mag[:, :n] - target_mag[:, :n]
    return float(np.linalg.norm(diff) / (np.linalg.norm(target_mag[:, :n]) + 1e-12))


def image_to_magnitude(path: str | Path, sr: int,
                       config: SpectroConfig | None = None,
                       n_frames: int = 800,
                       fmin: float = 150.0, fmax: float = 6000.0,
                       dynamic_db: float = 55.0) -> np.ndarray:
    """把一张照片编码成幅度谱——听得见的照片。

    亮度线性映射到 dB，暗部压到 -dynamic_db，这样图像的高光才有足够
    能量在听感上立得住。频率方向按对数排布，因为人耳是对数的，
    线性排布会把照片挤成一条细线。
    """
    from PIL import Image

    cfg = config or SpectroConfig(kind="stft")
    n_bins = cfg.n_fft // 2 + 1
    freqs = librosa.fft_frequencies(sr=sr, n_fft=cfg.n_fft)

    # 先把图缩成 (n_rows, n_frames)，行对应对数频率刻度
    n_rows = 512
    img = Image.open(path).convert("L").resize((n_frames, n_rows), Image.LANCZOS)
    L = np.asarray(img, dtype=np.float64)[::-1] / 255.0

    db = -dynamic_db * (1.0 - L)
    amp_rows = 10 ** (db / 20.0)

    # 对数行刻度 → 线性 FFT 频点
    row_f = np.logspace(np.log10(fmin), np.log10(fmax), n_rows)
    mag = np.zeros((n_bins, n_frames))
    inside = (freqs >= fmin) & (freqs <= fmax)
    for j in range(n_frames):
        mag[inside, j] = np.interp(freqs[inside], row_f, amp_rows[:, j])

    return mag


def write_wav(path: str | Path, y: np.ndarray, sr: int,
              normalize: bool = True) -> Path:
    """写出波形，默认做峰值归一化避免削顶。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = np.asarray(y, dtype=np.float32)
    if normalize:
        peak = float(np.max(np.abs(out)))
        if peak > 0:
            out = out / peak * 0.95
    sf.write(path, out, sr)
    return path
