"""生成在线 Demo 用的两段示例音频（docs/samples/）。

  demo-genuine.flac  demo_track.wav 的前 5 小节（12 s），加两路不同的短回声做成立体声，
                     16-bit FLAC —— 从没经过有损编码，spf audit 判 clean。
  demo-128k.mp3      同一段音频经 LAME 128 kbps 编码。页面把它当成"转回 FLAC 的 mp3"来分析
                     （浏览器解码后的 PCM 与 mp3→FLAC 转码逐样本相同），spf audit 判 suspect。

为什么要做成立体声：单声道 128k 的 LAME 低通在 20 kHz 附近（落在模糊带，只判 likely），
立体声才会切在典型的 16 kHz 左右，这正是网上最常见的"假无损"。

需要 ffmpeg（libmp3lame）。重新生成：python examples/make_web_samples.py
"""
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

here = Path(__file__).resolve().parent
out = here.parent / "docs" / "samples"
out.mkdir(parents=True, exist_ok=True)

y, sr = sf.read(here / "demo_track.wav", dtype="float64")
y = y[: int(12.0 * sr)]            # 5 小节 × 2.4 s

def echo(x, ms, gain):
    d = int(sr * ms / 1000)
    e = np.zeros_like(x)
    e[d:] = x[:-d]
    return gain * e

left = 0.8 * y + echo(y, 11, 0.35) + echo(y, 37, 0.18)
right = 0.8 * y + echo(y, 17, 0.35) + echo(y, 29, 0.18)
st = np.stack([left, right], axis=1)
fade = int(0.05 * sr)              # 尾部 50 ms 淡出，循环播放不爆音
st[-fade:] *= np.linspace(1, 0, fade)[:, None]
st *= 0.9 / np.max(np.abs(st))

sf.write(out / "demo-genuine.flac", st, sr, subtype="PCM_16")

with tempfile.TemporaryDirectory() as tmp:
    wav = Path(tmp) / "src.wav"
    sf.write(wav, st, sr, subtype="PCM_16")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-map_metadata", "-1",
         "-c:a", "libmp3lame", "-b:a", "128k", str(out / "demo-128k.mp3")],
        check=True,
    )

for p in sorted(out.iterdir()):
    print(f"{p.name:22s} {p.stat().st_size / 1024:7.0f} KB")
