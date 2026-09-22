"""生成 README 里的转码悬崖对比图。

自给自足：用 ffmpeg 现场造一组 ground truth（同一段音频、不同低通截止、
再转回 FLAC），然后把各自的长时谱画在一起。图里那几道垂直的悬崖，
就是 `spf audit` 赖以判断的全部依据。

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spectral_forensics.audit import find_cutoff, long_term_spectrum
from spectral_forensics.io import load_raw

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "demo_track.wav"
OUT = HERE / "audit_cliffs.png"
SR = 44100

# (ffmpeg 低通截止, 图例标签, 颜色)
CASES: list[tuple[int | None, str, str]] = [
    (None,  "genuine (no encoder)", "#ffe6a7"),
    (19000, "→ mp3 ~192 kbps",      "#f2813c"),
    (16000, "→ mp3 ~128 kbps",      "#b83355"),
    (13000, "→ mp3 ~96 kbps",       "#c264a8"),
]


def build_ground_truth(workdir: Path) -> list[tuple[Path, str, str]]:
    """把同一段源音频编码成几种码率，再转回 FLAC。"""
    made = []
    for cutoff, label, color in CASES:
        if cutoff is None:
            dst = workdir / "genuine.flac"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                            "-i", str(SOURCE), str(dst)], check=True)
        else:
            mp3 = workdir / f"enc_{cutoff}.mp3"
            dst = workdir / f"cut_{cutoff}.flac"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(SOURCE),
                            "-codec:a", "libmp3lame", "-b:a", "128k",
                            "-cutoff", str(cutoff), str(mp3)], check=True)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                            "-i", str(mp3), str(dst)], check=True)
        made.append((dst, label, color))
    return made


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("需要 ffmpeg 来生成 ground truth，请先安装。", file=sys.stderr)
        return 1
    if not SOURCE.exists():
        print("缺少源音频，请先运行 make_demo_audio.py", file=sys.stderr)
        return 1

    bg = "#05070d"
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=180, facecolor=bg)
    ax.set_facecolor(bg)

    with tempfile.TemporaryDirectory() as tmp:
        for path, label, color in build_ground_truth(Path(tmp)):
            y, sr = load_raw(path, sr=SR, mono=True)
            freqs, db = long_term_spectrum(y, sr)

            band = (freqs >= 200) & (freqs <= 4000)
            rel = db - db[band].max()

            f_c, steep = find_cutoff(freqs, db)
            detected = "" if f_c is None or f_c > 0.95 * sr / 2 \
                else f"   detected {f_c/1000:.1f} kHz, −{steep:.0f} dB/kHz"

            ax.semilogx(freqs[1:], rel[1:], color=color, lw=1.4,
                        label=label + detected)

    ax.set_xlim(50, SR / 2)
    ax.set_ylim(-100, 6)
    fg = "#8b93a7"
    ax.set_xlabel("Frequency (Hz)", color=fg, fontsize=9)
    ax.set_ylabel("Level relative to 200–4000 Hz peak (dB)", color=fg, fontsize=9)
    ax.tick_params(colors=fg, labelsize=8)
    ax.grid(True, which="both", color="#161b2b", lw=0.6)
    for s in ax.spines.values():
        s.set_visible(False)

    leg = ax.legend(loc="lower left", frameon=False, fontsize=8.5)
    for text, (_, _, color) in zip(leg.get_texts(), CASES):
        text.set_color(color)

    ax.set_title("Every lossy encoder leaves a cliff — and the cliff survives "
                 "conversion back to FLAC",
                 color="#f0f2f8", fontsize=11, pad=14, loc="left")

    fig.tight_layout()
    fig.savefig(OUT, facecolor=bg)
    plt.close(fig)
    print(f"已生成 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
