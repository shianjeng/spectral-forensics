"""渲染：时频矩阵 → 图像。

本模块只接受 numpy 数组，不碰音频解码。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from .transform import Spectrogram

# 自带几组感知均匀的渐变。绝对不要用 jet：它在感知上不均匀，
# 会在平滑数据里造出根本不存在的"条纹"。
PALETTES: dict[str, list[str]] = {
    "ember": ["#05070d", "#1b1035", "#5c1d5c", "#b83355", "#f2813c", "#ffe6a7"],
    "abyss": ["#03050a", "#0a2540", "#136f8c", "#3fbfa0", "#c9f2c7"],
    "mono": ["#000000", "#2a2a2a", "#666666", "#b0b0b0", "#ffffff"],
    "bloom": ["#0a0510", "#2d1b4e", "#6b3fa0", "#c264a8", "#ffb3c6", "#fff0f3"],
}


def get_cmap(name: str):
    """取色板：优先用自带渐变，否则回落到 matplotlib 内置名。"""
    if name in PALETTES:
        return LinearSegmentedColormap.from_list(name, PALETTES[name], N=512)
    return plt.get_cmap(name)


def _freq_ticks(spec: Spectrogram) -> tuple[list[float], list[str]]:
    """在对数感知的频率轴上挑几个整数刻度。"""
    candidates = [50, 100, 250, 500, 1000, 2000, 4000, 8000, 16000]
    lo, hi = spec.freqs[0], spec.freqs[-1]
    min_gap = len(spec.freqs) * 0.045  # 行号间距小于这个就丢弃，避免标签叠字
    pos: list[float] = []
    lab: list[str] = []
    for f in candidates:
        if not (lo < f < hi):
            continue
        # 频率轴非线性，用插值找到对应的行号
        row = float(np.interp(f, spec.freqs, np.arange(len(spec.freqs))))
        if pos and row - pos[-1] < min_gap:
            continue
        pos.append(row)
        lab.append(f"{f // 1000}k" if f >= 1000 else str(f))
    return pos, lab


def poster(
    spec: Spectrogram,
    out_path: str | Path,
    title: str = "",
    subtitle: str = "",
    palette: str = "ember",
    width: float = 12.0,
    height: float = 8.0,
    dpi: int = 200,
    show_axes: bool = True,
    background: str = "#05070d",
) -> Path:
    """把整段音频画成一张静态"声纹海报"。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmap = get_cmap(palette)
    fig = plt.figure(figsize=(width, height), dpi=dpi, facecolor=background)

    if show_axes:
        ax = fig.add_axes((0.08, 0.14, 0.88, 0.70))
    else:
        ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))

    ax.imshow(
        spec.S_db,
        origin="lower",
        aspect="auto",
        cmap=cmap,
        interpolation="nearest",
        extent=(0.0, float(spec.times[-1]), 0.0, float(spec.S_db.shape[0])),
    )
    ax.set_facecolor(background)

    if show_axes:
        fg = "#8b93a7"
        ypos, ylab = _freq_ticks(spec)
        ax.set_yticks(ypos)
        ax.set_yticklabels(ylab, color=fg, fontsize=8)
        ax.set_ylabel("Frequency (Hz)", color=fg, fontsize=9, labelpad=8)

        dur = float(spec.times[-1])
        step = max(15, round(dur / 8 / 15) * 15)
        xticks = np.arange(0, dur, step)
        ax.set_xticks(xticks)
        ax.set_xticklabels(
            [f"{int(t) // 60}:{int(t) % 60:02d}" for t in xticks], color=fg, fontsize=8
        )
        ax.set_xlabel("Time", color=fg, fontsize=9, labelpad=6)

        for side in ax.spines.values():
            side.set_visible(False)
        ax.tick_params(length=0)

        if title:
            fig.text(
                0.08,
                0.90,
                title,
                color="#f0f2f8",
                fontsize=20,
                fontweight="bold",
                ha="left",
                va="bottom",
            )
        if subtitle:
            fig.text(
                0.08,
                0.055,
                subtitle,
                color="#5a6175",
                fontsize=7.5,
                ha="left",
                va="center",
                family="monospace",
            )
    else:
        ax.set_axis_off()

    fig.savefig(out_path, facecolor=background, dpi=dpi)
    plt.close(fig)
    return out_path


def comparison(
    specs: list[Spectrogram],
    labels: list[str],
    out_path: str | Path,
    palette: str = "ember",
    dpi: int = 160,
    background: str = "#05070d",
) -> Path:
    """并排对比多组参数——README 里讲不确定性关系全靠这张图。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = len(specs)
    cmap = get_cmap(palette)
    fig, axes = plt.subplots(
        n, 1, figsize=(11, 2.6 * n), dpi=dpi, facecolor=background, squeeze=False
    )

    for ax, spec, label in zip(axes[:, 0], specs, labels):
        ax.imshow(
            spec.S_db,
            origin="lower",
            aspect="auto",
            cmap=cmap,
            interpolation="nearest",
            extent=(0.0, float(spec.times[-1]), 0.0, float(spec.S_db.shape[0])),
        )
        ax.set_facecolor(background)
        ax.set_xticks([])
        ax.set_yticks([])
        for side in ax.spines.values():
            side.set_visible(False)
        ax.text(
            0.012,
            0.88,
            label,
            transform=ax.transAxes,
            color="#ffe6a7",
            fontsize=9,
            family="monospace",
            va="top",
        )

    fig.tight_layout(pad=0.6)
    fig.savefig(out_path, facecolor=background, dpi=dpi)
    plt.close(fig)
    return out_path
