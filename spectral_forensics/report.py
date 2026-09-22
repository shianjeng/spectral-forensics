"""把整库扫描结果导出成一份可分享的 HTML 报告。

终端输出在五万个文件面前是不够用的——滚上去就找不着了，也没法发给别人。
这份报告是单文件、自包含的：每个可疑文件带一张自己的长时谱缩略图，
悬崖画在图上，截图发到论坛就能当证据。
"""

from __future__ import annotations

import base64
import html
import io
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from .audit import AuditResult, long_term_spectrum
from .io import load_raw

BG = "#05070d"
PANEL = "#0b0f1a"
LINE = "#161b2b"
FG = "#f0f2f8"
DIM = "#8b93a7"
FAINT = "#5a6175"

TIER = {
    "suspect": ("⚠", "#b83355", "Suspect"),
    "likely": ("?", "#ffe6a7", "Likely"),
    "lossy": ("·", "#8b93a7", "Lossy container"),
    "clean": ("✓", "#3fbfa0", "Clean"),
    "unknown": ("!", "#5a6175", "Unreadable"),
}


def _thumbnail(
    path: Path, cutoff_khz: float | None, sr: int = 44100, seconds: float = 60.0
) -> str | None:
    """画一张小的长时谱，返回内嵌用的 data URI。失败就返回 None。"""
    try:
        y, sr_actual = load_raw(path, sr=sr, mono=True, duration=seconds)
        freqs, db = long_term_spectrum(y, sr_actual)
    except (OSError, RuntimeError, TypeError, ValueError):
        # 画不出缩略图不该让整份报告失败——这一条目照常列出，只是没有图
        return None

    band = (freqs >= 200) & (freqs <= 4000)
    if not band.any():
        return None
    rel = db - db[band].max()

    fig, ax = plt.subplots(figsize=(4.4, 1.5), dpi=130, facecolor=PANEL)
    ax.set_facecolor(PANEL)
    ax.semilogx(freqs[1:], rel[1:], color="#f2813c", lw=1.0)

    if cutoff_khz is not None and cutoff_khz * 1000 < 0.97 * sr_actual / 2:
        ax.axvline(cutoff_khz * 1000, color="#b83355", lw=1.2, ls="--")

    ax.set_xlim(50, sr_actual / 2)
    ax.set_ylim(-100, 5)
    ax.set_xticks([100, 1000, 10000])
    ax.set_xticklabels(["100", "1k", "10k"], color=FAINT, fontsize=6)
    ax.set_yticks([0, -50, -100])
    ax.set_yticklabels(["0", "-50", "-100"], color=FAINT, fontsize=6)
    ax.tick_params(length=0)
    ax.grid(True, which="both", color=LINE, lw=0.4)
    for s in ax.spines.values():
        s.set_visible(False)

    buf = io.BytesIO()
    fig.tight_layout(pad=0.2)
    fig.savefig(buf, format="png", facecolor=PANEL)
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _row(r: AuditResult, thumb: str | None) -> str:
    mark, color, _label = TIER.get(r.verdict, TIER["unknown"])
    name = html.escape(Path(r.path).name)
    parent = html.escape(str(Path(r.path).parent))
    cut = f"{r.cutoff_khz:.1f} kHz" if r.cutoff_khz else "—"
    steep = f"−{r.steepness_db:.0f} dB" if r.steepness_db is not None else "—"
    conf = f"{r.confidence:.0%}" if r.verdict in ("suspect", "likely") else ""
    guess = html.escape(r.guess) if r.guess and r.guess != "—" else ""
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in r.notes)

    img = (
        f'<img src="{thumb}" alt="long-term spectrum of {name}">'
        if thumb
        else '<div class="nothumb">no spectrum</div>'
    )

    return f"""
<article class="row {r.verdict}">
  <div class="meta">
    <div class="head"><span class="mark" style="color:{color}">{mark}</span>
      <span class="name">{name}</span>
      <span class="conf">{conf}</span></div>
    <div class="dir">{parent}</div>
    <div class="facts"><span>cutoff <b>{cut}</b></span>
      <span>falloff <b>{steep}</b></span>
      <span>codec <b>{html.escape(r.codec)}</b></span></div>
    {f'<div class="guess">{guess}</div>' if guess else ""}
    {f'<ul class="notes">{notes}</ul>' if notes else ""}
  </div>
  <div class="thumb">{img}</div>
</article>"""


def build_report(
    results: list[AuditResult],
    root: str | Path,
    thumbnails: bool = True,
    thumb_limit: int = 200,
) -> str:
    """生成完整的 HTML 文本。"""
    counts = Counter(r.verdict for r in results)
    order = {"suspect": 0, "likely": 1, "lossy": 2, "unknown": 3, "clean": 4}
    ordered = sorted(results, key=lambda r: (order.get(r.verdict, 9), r.path))

    rows, drawn = [], 0
    for r in ordered:
        thumb = None
        if thumbnails and r.verdict in ("suspect", "likely") and drawn < thumb_limit:
            thumb = _thumbnail(Path(r.path), r.cutoff_khz)
            drawn += 1
        rows.append(_row(r, thumb))

    def chip(key: str) -> str:
        if not counts.get(key):
            return ""
        _, color, label = TIER[key]
        return (
            f'<span class="chip" style="border-color:{color};color:{color}">'
            f"{counts[key]} {label.lower()}</span>"
        )

    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Transcode audit — {html.escape(str(root))}</title>
<style>
:root{{box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);
      padding-bottom:env(safe-area-inset-bottom,0px)}}
*,*::before,*::after{{box-sizing:inherit}}
body{{margin:0;background:{BG};color:{FG};
  font:14px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}}
.wrap{{max-width:940px;margin:0 auto;padding:40px 18px 70px}}
h1{{font-size:24px;margin:0 0 6px;letter-spacing:-.02em}}
.sub{{color:{FAINT};font-size:13px;margin:0 0 18px;word-break:break-all}}
.chips{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:26px}}
.chip{{border:1px solid;border-radius:999px;padding:3px 11px;font-size:12px}}
.row{{display:flex;gap:18px;align-items:flex-start;background:{PANEL};
  border:1px solid {LINE};border-radius:12px;padding:16px;margin-bottom:12px;
  flex-wrap:wrap}}
.meta{{flex:1 1 320px;min-width:0}}
.head{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}}
.mark{{font-size:17px}}
.name{{font-weight:600;word-break:break-all}}
.conf{{color:{FAINT};font-size:12px}}
.dir{{color:{FAINT};font-size:11.5px;word-break:break-all;margin:2px 0 8px}}
.facts{{display:flex;gap:18px;flex-wrap:wrap;color:{DIM};font-size:12.5px}}
.facts b{{color:{FG};font-weight:600}}
.guess{{margin-top:8px;color:#f2813c;font-size:13px}}
ul.notes{{margin:8px 0 0;padding-left:17px;color:{DIM};font-size:12.5px}}
.thumb{{flex:0 0 auto;max-width:100%;overflow-x:auto}}
.thumb img{{display:block;max-width:100%;border-radius:8px}}
.nothumb{{color:{FAINT};font-size:12px}}
footer{{margin-top:34px;border-top:1px solid {LINE};padding-top:18px;
  color:{FAINT};font-size:12.5px}}
a{{color:#f2813c}}
</style></head><body><div class="wrap">
<h1>Transcode audit</h1>
<p class="sub">{html.escape(str(root))} · {len(results)} files · {stamp}</p>
<div class="chips">{chip("suspect")}{chip("likely")}{chip("lossy")}{chip("unknown")}{chip("clean")}</div>
{"".join(rows)}
<footer>
Generated by <a href="https://github.com/shianjeng/spectral-forensics">spectral-forensics</a>.
A <b>clean</b> verdict means no lowpass evidence was found, not proof of provenance —
encoders that apply no hard lowpass pass this test. Dashed line marks the detected cutoff.
</footer>
</div></body></html>"""


def write_report(
    results: list[AuditResult], out_path: str | Path, root: str | Path, **kwargs
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_report(results, root, **kwargs), encoding="utf-8")
    return out_path
