"""生成 README 里的转码悬崖图（examples/audit_cliffs.png）。

同一段 12 秒的立体声片段（与在线 Demo 的示例相同），用 LAME 以 96 / 128 / 192 kbps
真实编码、再转回 FLAC：

  上：真无损与 128 kbps 往返后的时频图，线性频率轴——mp3 那一版在截止频率以上是一整块黑。
  下：8–22 kHz 的长时谱。真无损一直延伸到顶，每个码率在各自的截止频率掉下悬崖；
      图上标的数值就是 spf audit 检测到的截止频率。

用立体声而不是单声道：LAME 对单声道 128k 的低通在 20 kHz 附近（落在模糊带），
立体声才是网上最常见的“假无损”那种 16 kHz 左右的截止。

版式与在线 Demo 一致：纸色底、墨线、等宽数字，绘图区保持深色，像贴在测量报告里的截图。

需要带 libmp3lame 的 ffmpeg。装了 fontTools（和 brotli）时使用 docs/fonts 里的
Geist / Geist Mono，与网页一致；没有就退回 matplotlib 的默认字体。

    python examples/make_audit_figure.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from matplotlib import font_manager
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spectral_forensics.audit import find_cutoff, long_term_spectrum
from spectral_forensics.render import get_cmap

SOURCE = ROOT / "examples" / "demo_track.wav"
OUT = ROOT / "examples" / "audit_cliffs.png"
CLIP_S = 12.0

# 纸面（与 docs/index.html 的报告样式相同）
PAPER, INK, INK2, INK3 = "#faf9f5", "#17171b", "#46474e", "#77787f"
# 深色绘图区里的颜色（与网页画布相同）
WELL, ON_WELL, GRID = "#07080c", "#aab0c3", (1.0, 1.0, 1.0, 0.08)
MINT, GOLD, EMBER, ROSE = "#4fd1ae", "#f3d38b", "#f2813c", "#ff6b8a"
BITRATES: list[tuple[int, str]] = [(192, GOLD), (128, EMBER), (96, ROSE)]


def site_fonts() -> tuple[str, str]:
    """把 docs/fonts 里的 woff2 转成 matplotlib 能读的 TTF，返回 (正文, 等宽) 字体名。"""
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
    except ImportError:
        return "DejaVu Sans", "DejaVu Sans Mono"
    fonts, tmp = ROOT / "docs" / "fonts", Path(tempfile.mkdtemp(prefix="spf-fonts-"))
    try:
        for name, weights in (("geist", (400, 600)), ("geist-mono", (400, 600))):
            for weight in weights:
                font = TTFont(fonts / f"{name}.woff2")
                font.flavor = None
                static = instancer.instantiateVariableFont(font, {"wght": weight})
                static["OS/2"].usWeightClass = weight
                path = tmp / f"{name}-{weight}.ttf"
                static.save(path)
                font_manager.fontManager.addfont(str(path))
    except Exception as err:  # noqa: BLE001 —— 字体只是锦上添花
        print(f"网页字体不可用，改用默认字体：{err}", file=sys.stderr)
        return "DejaVu Sans", "DejaVu Sans Mono"
    return "Geist", "Geist Mono"


def stereo_clip() -> tuple[np.ndarray, int]:
    """与 make_web_samples.py 相同的立体声片段：左右各加两路不同的短回声。"""
    y, sr = sf.read(SOURCE, dtype="float64")
    y = y[: int(CLIP_S * sr)]

    def echo(x: np.ndarray, ms: float, gain: float) -> np.ndarray:
        d = int(sr * ms / 1000)
        e = np.zeros_like(x)
        e[d:] = x[:-d]
        return gain * e

    left = 0.8 * y + echo(y, 11, 0.35) + echo(y, 37, 0.18)
    right = 0.8 * y + echo(y, 17, 0.35) + echo(y, 29, 0.18)
    st = np.stack([left, right], axis=1)
    return st * (0.9 / np.max(np.abs(st))), sr


def round_trips(st: np.ndarray, sr: int, workdir: Path) -> dict[str, np.ndarray]:
    """真无损（16-bit PCM）以及各码率 mp3 转回 FLAC 后的单声道信号。"""
    src = workdir / "genuine.wav"
    sf.write(src, st, sr, subtype="PCM_16")
    out = {"genuine": sf.read(src, dtype="float64")[0].mean(axis=1)}
    for br, _ in BITRATES:
        mp3, flac = workdir / f"{br}.mp3", workdir / f"{br}.flac"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                        "-c:a", "libmp3lame", "-b:a", f"{br}k", str(mp3)], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), str(flac)], check=True)
        y, got = sf.read(flac, dtype="float64")
        assert got == sr
        out[str(br)] = y.mean(axis=1)[: len(out["genuine"])]
    return out


def stft_db(y: np.ndarray, ref: float, n_fft: int = 2048, hop: int = 256) -> np.ndarray:
    """功率时频图（dB，相对 ref），低于 −100 dB 的截掉。"""
    frames = np.lib.stride_tricks.sliding_window_view(y, n_fft)[::hop] * np.hanning(n_fft)
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    return np.maximum(10 * np.log10(power.T / ref + 1e-12), -100.0)


def spectrum(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, float | None]:
    """spf audit 用的长时谱，相对 200–4000 Hz 峰值；另给出它检测到的截止频率。"""
    freqs, db = long_term_spectrum(y, sr)
    band = (freqs >= 200) & (freqs <= 4000)
    cutoff, _ = find_cutoff(freqs, db)
    return freqs, db - db[band].max(), cutoff


def smooth(x: np.ndarray, n: int = 15) -> np.ndarray:
    """画图用的滑动平均（约 80 Hz），只去掉毛刺，不改变悬崖的位置。"""
    pad = np.pad(x, n // 2, mode="edge")
    return np.convolve(pad, np.ones(n) / n, mode="valid")


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("需要带 libmp3lame 的 ffmpeg，请先安装。", file=sys.stderr)
        return 1
    if not SOURCE.exists():
        print("缺少源音频，请先运行 make_demo_audio.py", file=sys.stderr)
        return 1

    sans, mono = site_fonts()
    plt.rcParams.update({"font.family": sans, "font.size": 12, "axes.unicode_minus": True})

    st, sr = stereo_clip()
    with tempfile.TemporaryDirectory() as tmp:
        sig = round_trips(st, sr, Path(tmp))

    nyq_k = sr / 2000
    spectra = {k: spectrum(y, sr) for k, y in sig.items()}
    for k, (_, _, fc) in spectra.items():
        full = fc is None or fc > 0.98 * sr / 2
        print(f"{k:>8}: 检测到的截止频率 {'全频带' if full else f'{fc / 1000:.2f} kHz'}")

    fig = plt.figure(figsize=(11, 8.4), dpi=170, facecolor=PAPER)
    gs = GridSpec(2, 2, figure=fig, height_ratios=[1, 1.08], hspace=0.40, wspace=0.07,
                  left=0.075, right=0.965, top=0.735, bottom=0.07)

    # 报告页头：外框、刊头、标题
    fig.add_artist(Rectangle((0.004, 0.004), 0.992, 0.992, transform=fig.transFigure,
                             fill=False, ec=INK, lw=1.2))
    fig.add_artist(Line2D([0.004, 0.996], [0.938, 0.938], transform=fig.transFigure, color=INK, lw=1))
    fig.text(0.035, 0.958, "spectral-forensics", family=mono, weight=600, size=11, color=INK, va="center")
    fig.text(0.205, 0.958, "|  Transcode audit", family=mono, size=11, color=INK3, va="center")
    fig.text(0.965, 0.958, "python examples/make_audit_figure.py", family=mono, size=10,
             color=INK3, va="center", ha="right")
    fig.text(0.075, 0.895, "Every lossy encoder leaves a cliff", size=25, weight=600, color=INK, va="top")
    fig.text(0.075, 0.842, "Converting the file back to FLAC does not remove it. The same 12-second clip, "
             "encoded with LAME and decoded back to lossless.", size=12, color=INK2, va="top")

    def fig_label(ax, no: str, title: str) -> None:
        """“Fig. 1  标题”：编号用等宽浅色，标题用正文粗体，和网页的图头一样。"""
        r = fig.canvas.get_renderer()
        t = ax.text(0, 1.03, no, transform=ax.transAxes, family=mono, size=11, color=INK3, va="bottom")
        x1 = t.get_window_extent(r).transformed(ax.transAxes.inverted()).x1
        ax.text(x1 + 10 / ax.bbox.width, 1.03, title, transform=ax.transAxes,
                size=13, weight=600, color=INK, va="bottom")

    def frame(ax) -> None:
        ax.set_facecolor(WELL)
        for spine in ax.spines.values():
            spine.set_color(INK)
            spine.set_linewidth(1)
        ax.tick_params(colors=INK3, labelsize=10, length=0, pad=6)
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            lbl.set_fontfamily(mono)

    # ---- 上：两张时频图，共用同一个 0 dB 参考 ----
    ref = float(np.max(np.abs(np.fft.rfft(np.hanning(2048) * 0.9)) ** 2))
    cut128 = spectra["128"][2]
    cmap = get_cmap("ember")
    for col, (key, no, title) in enumerate([
        ("genuine", "Fig. 1", "Genuine FLAC"),
        ("128", "Fig. 2", "128 kbps mp3, back to FLAC"),
    ]):
        ax = fig.add_subplot(gs[0, col])
        dur = len(sig[key]) / sr
        ax.imshow(stft_db(sig[key], ref), origin="lower", aspect="auto", cmap=cmap,
                  vmin=-92, vmax=-32, extent=(0, dur, 0, nyq_k),
                  interpolation="bilinear", rasterized=True)
        ax.set_yticks([0, 5, 10, 15, 20])
        ax.set_yticklabels(["0", "5", "10", "15", "20 kHz"] if col == 0 else [])
        ax.set_xticks([0, 4, 8, 12])
        ax.set_xticklabels(["0" if col == 0 else "", "4", "8", "12 s"])
        frame(ax)
        fig_label(ax, no, title)
        if key == "128" and cut128:
            k = cut128 / 1000
            ax.axhline(k, color=ROSE, lw=1.4, ls=(0, (6, 4)))
            ax.text(dur / 2, (k + nyq_k) / 2, f"nothing above {k:.1f} kHz",
                    ha="center", va="center", color=ROSE, size=13, weight=600)

    # ---- 下：8–22 kHz 长时谱 ----
    ax = fig.add_subplot(gs[1, :])
    f_gen, r_gen, _ = spectra["genuine"]
    khz = f_gen / 1000
    view = (khz >= 7.9) & (khz <= nyq_k - 0.15)
    plateau = float(np.median(smooth(r_gen)[(khz >= 9) & (khz <= 14)]))
    top = float(np.ceil((plateau + 34) / 10) * 10)

    for br, color in BITRATES:          # 编码版本先画，真无损压在最上面一路走到顶
        f, r, _ = spectra[str(br)]
        ax.plot(f[view] / 1000, smooth(r)[view], color=color, lw=2.0,
                solid_joinstyle="round", zorder=2)
    ax.plot(khz[view], smooth(r_gen)[view], color=MINT, lw=1.6, zorder=3)

    label_y = plateau + 20
    for br, color in BITRATES:
        fc = spectra[str(br)][2]
        if fc is None:
            continue
        k = fc / 1000
        ax.plot([k, k], [plateau + 4, label_y - 5], color=color, lw=1, ls=(0, (2, 2)), zorder=1)
        ax.text(k, label_y + 5, f"{br} kbps", ha="center", va="bottom",
                color=color, size=13, weight=600)
        ax.text(k, label_y + 4.5, f"{k:.1f} kHz", ha="center", va="top",
                color=ON_WELL, size=11, family=mono)
    ax.text(21.95, label_y + 5, "genuine", ha="right", va="bottom",
            color=MINT, size=13, weight=600)
    ax.text(21.95, label_y + 4.5, "full band", ha="right", va="top", color=ON_WELL, size=11)

    ax.set_xlim(8, 22)
    ax.set_ylim(-100, top)
    xt = np.arange(8, 21, 2)
    ax.set_xticks(xt)
    ax.set_xticklabels([f"{v:.0f}" for v in xt[:-1]] + [f"{xt[-1]:.0f} kHz"])
    yt = np.arange(-100, top + 1, 20)
    ax.set_yticks(yt)
    ax.set_yticklabels([f"{v:.0f} dB".replace("-", "−") for v in yt])
    ax.grid(True, color=GRID, lw=0.8)
    frame(ax)
    fig_label(ax, "Fig. 3", "Long-term spectrum, 8–22 kHz · the numbers are what spf audit detects")

    fig.savefig(OUT, facecolor=PAPER)
    plt.close(fig)
    print(f"已生成 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
