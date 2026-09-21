"""时频变换：STFT / 梅尔谱 / CQT。

本模块只吐 numpy 数组，不碰任何绘图逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import librosa
import numpy as np

from .io import Audio

TransformKind = Literal["stft", "mel", "cqt"]


@dataclass(frozen=True)
class SpectroConfig:
    """时频变换的全部参数。

    n_fft / hop_length 是整个项目最核心的一对旋钮，它们之间是不确定性关系：

        Δt · Δf ≳ 1/2

    具体地，帧长 N 个采样点对应
        时间分辨率  Δt = N / sr
        频率分辨率  Δf = sr / N
    两者乘积恒为 1，调大一个必然牺牲另一个。

    sr=22050 时：
        n_fft=1024 → Δt≈46ms,  Δf≈21.5Hz   鼓点清晰，低音和弦糊成一团
        n_fft=2048 → Δt≈93ms,  Δf≈10.8Hz   通用默认值
        n_fft=4096 → Δt≈186ms, Δf≈5.4Hz    谐波线锐利，瞬态被抹平
    """

    kind: TransformKind = "mel"
    n_fft: int = 2048
    hop_length: int = 512
    window: str = "hann"
    n_mels: int = 128            # 仅 kind="mel"
    fmin: float = 20.0
    fmax: float | None = None    # None → sr/2
    bins_per_octave: int = 36    # 仅 kind="cqt"，36 = 每半音 3 个频点
    n_octaves: int = 7           # 仅 kind="cqt"
    top_db: float = 80.0         # dB 动态范围裁剪

    def time_resolution(self, sr: int) -> float:
        """单帧覆盖的时间跨度（秒）。"""
        return self.n_fft / sr

    def freq_resolution(self, sr: int) -> float:
        """相邻频点的间隔（Hz）。"""
        return sr / self.n_fft

    def describe(self, sr: int) -> str:
        """一行人类可读的参数说明，印在海报角落。"""
        return (f"{self.kind.upper()} · n_fft={self.n_fft} · hop={self.hop_length} "
                f"· {self.window} · Δt={self.time_resolution(sr) * 1000:.0f}ms "
                f"· Δf={self.freq_resolution(sr):.1f}Hz")


@dataclass(frozen=True)
class Spectrogram:
    """时频矩阵及其坐标轴。"""

    S_db: np.ndarray             # (n_freq, n_frames)，单位 dB
    times: np.ndarray            # 每帧中心时刻（秒）
    freqs: np.ndarray            # 每行对应的频率（Hz）
    sr: int
    config: SpectroConfig = field(repr=False)

    @property
    def shape(self) -> tuple[int, int]:
        return self.S_db.shape


def compute(audio: Audio, config: SpectroConfig | None = None) -> Spectrogram:
    """按配置计算时频表示，输出已转 dB 并裁剪动态范围。"""
    cfg = config or SpectroConfig()
    fmax = cfg.fmax if cfg.fmax is not None else audio.sr / 2

    if cfg.kind == "stft":
        D = librosa.stft(audio.y, n_fft=cfg.n_fft,
                         hop_length=cfg.hop_length, window=cfg.window)
        S_power = np.abs(D) ** 2
        freqs = librosa.fft_frequencies(sr=audio.sr, n_fft=cfg.n_fft)

    elif cfg.kind == "mel":
        # 梅尔刻度近似人耳感知：低频密、高频疏。
        # 线性频率轴下，80% 的像素会浪费在 5kHz 以上几乎没有内容的区域。
        S_power = librosa.feature.melspectrogram(
            y=audio.y, sr=audio.sr, n_fft=cfg.n_fft,
            hop_length=cfg.hop_length, window=cfg.window,
            n_mels=cfg.n_mels, fmin=cfg.fmin, fmax=fmax,
        )
        freqs = librosa.mel_frequencies(n_mels=cfg.n_mels, fmin=cfg.fmin, fmax=fmax)

    elif cfg.kind == "cqt":
        # 常数 Q 变换：每个倍频程的频点数固定，正好对应十二平均律。
        # 画和弦、旋律线比 STFT 清楚得多，代价是慢。
        n_bins = cfg.bins_per_octave * cfg.n_octaves
        C = librosa.cqt(audio.y, sr=audio.sr, hop_length=cfg.hop_length,
                        fmin=max(cfg.fmin, librosa.note_to_hz("C1")),
                        n_bins=n_bins, bins_per_octave=cfg.bins_per_octave)
        S_power = np.abs(C) ** 2
        freqs = librosa.cqt_frequencies(
            n_bins=n_bins,
            fmin=max(cfg.fmin, librosa.note_to_hz("C1")),
            bins_per_octave=cfg.bins_per_octave,
        )
    else:
        raise ValueError(f"未知的变换类型: {cfg.kind}")

    # 功率动态范围能跨 6 个数量级，不转 dB 的话整张图是一片黑加几个亮点。
    S_db = librosa.power_to_db(S_power, ref=np.max, top_db=cfg.top_db)
    times = librosa.frames_to_time(np.arange(S_db.shape[1]),
                                   sr=audio.sr, hop_length=cfg.hop_length)

    return Spectrogram(S_db=S_db, times=times, freqs=freqs,
                       sr=audio.sr, config=cfg)


def frame_spectrum(spec: Spectrogram, t: float) -> np.ndarray:
    """取 t 时刻那一帧的频谱列，给视频逐帧渲染用。"""
    idx = int(np.searchsorted(spec.times, t))
    idx = min(max(idx, 0), spec.S_db.shape[1] - 1)
    return spec.S_db[:, idx]
