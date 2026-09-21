"""重分配谱（reassigned spectrogram）。

普通谱图里，一条纯音总是画成一条有宽度的带——宽度就是 Δt·Δf ≥ 1 的直接后果，
是窗函数强加的模糊，不是信号本身的性质。

重分配的思路：STFT 每个格点不只有幅度，还有相位。对相位求偏导可以得到这个
格点内能量的真实"重心"：

    瞬时频率   ω̂ = ω - ∂φ/∂t      （频率方向的修正）
    群延迟     t̂ = t + ∂φ/∂ω      （时间方向的修正）

把每个格点的能量从它所在的方格搬到 (t̂, ω̂)，图像就能比不确定性下限更锐利。
这不违反物理：不确定性限制的是单个时频原子的展宽，不限制你对能量位置的
*估计精度*——就像衍射极限限制不了质心定位的精度一样。

代价：在多分量信号重叠或信噪比低的地方，相位导数不可靠，重分配点会乱飞，
所以必须按幅度设门限。
"""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from .io import Audio
from .transform import SpectroConfig, Spectrogram


@dataclass(frozen=True)
class ReassignedPoints:
    """重分配后的散点云。"""

    times: np.ndarray      # 每个点的修正时刻（秒）
    freqs: np.ndarray      # 每个点的修正频率（Hz）
    weights: np.ndarray    # 每个点的功率
    sr: int
    duration: float

    def __len__(self) -> int:
        return len(self.times)


def reassign(audio: Audio, config: SpectroConfig | None = None,
             mag_top_db: float = 60.0, enabled: bool = True) -> ReassignedPoints:
    """计算重分配谱，返回筛选后的散点云。

    mag_top_db 之下的格点直接丢弃：那些地方相位是噪声，修正量没有意义，
    保留它们只会在图上撒一层雪花。

    enabled=False 时关闭重分配，坐标退回格点中心——这条路径存在的唯一目的，
    是让对比图的两边走完全相同的分箱流程，差异只来自重分配本身。
    """
    cfg = config or SpectroConfig(kind="stft")

    if enabled:
        freqs, times, mags = librosa.reassigned_spectrogram(
            y=audio.y, sr=audio.sr, n_fft=cfg.n_fft,
            hop_length=cfg.hop_length, window=cfg.window,
            fill_nan=True, clip=True,
        )
    else:
        mags = np.abs(librosa.stft(audio.y, n_fft=cfg.n_fft,
                                   hop_length=cfg.hop_length, window=cfg.window))
        f_axis = librosa.fft_frequencies(sr=audio.sr, n_fft=cfg.n_fft)
        t_axis = librosa.frames_to_time(np.arange(mags.shape[1]),
                                        sr=audio.sr, hop_length=cfg.hop_length)
        freqs = np.repeat(f_axis[:, None], mags.shape[1], axis=1)
        times = np.repeat(t_axis[None, :], mags.shape[0], axis=0)

    power = mags ** 2
    db = librosa.power_to_db(power, ref=np.max, top_db=None)
    keep = (db > -mag_top_db) & np.isfinite(freqs) & np.isfinite(times)

    return ReassignedPoints(
        times=times[keep], freqs=freqs[keep],
        weights=power[keep], sr=audio.sr,
        duration=audio.duration,
    )


def rasterize(points: ReassignedPoints, n_time: int = 1400,
              n_freq: int = 600, fmin: float = 20.0,
              fmax: float | None = None, log_freq: bool = True,
              top_db: float = 80.0) -> Spectrogram:
    """把散点云落到规则网格上，好让 render.poster 直接画。

    频率方向默认用对数分箱：重分配的意义在于锐化谐波线，而谐波在对数轴上
    才是等间距的，线性分箱会把低频的锐度浪费掉。
    """
    fmax = fmax if fmax is not None else points.sr / 2

    if log_freq:
        edges_f = np.logspace(np.log10(max(fmin, 1.0)), np.log10(fmax), n_freq + 1)
    else:
        edges_f = np.linspace(fmin, fmax, n_freq + 1)
    edges_t = np.linspace(0.0, points.duration, n_time + 1)

    H, _, _ = np.histogram2d(
        points.times, points.freqs,
        bins=(edges_t, edges_f), weights=points.weights,
    )
    S_power = H.T   # → (n_freq, n_time)

    S_db = librosa.power_to_db(S_power + 1e-12, ref=np.max, top_db=top_db)
    centers_f = np.sqrt(edges_f[:-1] * edges_f[1:]) if log_freq else \
        0.5 * (edges_f[:-1] + edges_f[1:])
    centers_t = 0.5 * (edges_t[:-1] + edges_t[1:])

    return Spectrogram(S_db=S_db, times=centers_t, freqs=centers_f,
                       sr=points.sr, config=SpectroConfig(kind="stft"))


def sharpness(spec: Spectrogram) -> float:
    """谱图锐度指标：归一化后的谱平坦度倒数，越大越锐。

    用来定量说明"重分配后确实更锐了"，而不是只靠肉眼看图。
    """
    p = np.exp(spec.S_db / 10.0 * np.log(10.0))
    p = p / (p.sum() + 1e-20)
    entropy = -(p * np.log(p + 1e-20)).sum()
    return float(np.log(p.size) - entropy)   # 0 = 完全均匀，越大越集中
