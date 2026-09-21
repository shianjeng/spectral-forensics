"""逐帧渲染 + ffmpeg 管道合成带原音轨的 mp4。

关键性能决策：
1. 不用 matplotlib 逐帧画。一首 3 分钟的歌 30fps 是 5400 帧，
   每帧 Figure.canvas.draw() 几十毫秒起步，光渲染就要好几分钟。
2. 不存 png 中间文件。直接开一个 ffmpeg 子进程，把 numpy 的 RGB
   缓冲区 stdin.write() 喂进去，省掉磁盘 IO，能快一个量级。
这里用纯 numpy 光栅化柱状频谱，单帧约 1ms。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np

from .io import Audio
from .render import get_cmap
from .transform import Spectrogram


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _resample_rows(column: np.ndarray, n_out: int) -> np.ndarray:
    """把频谱列重采样成 n_out 根柱子。"""
    src = np.linspace(0.0, 1.0, len(column))
    dst = np.linspace(0.0, 1.0, n_out)
    return np.interp(dst, src, column)


def _draw_bars(levels: np.ndarray, width: int, height: int,
               lut: np.ndarray, bg: np.ndarray, gap: int = 2) -> np.ndarray:
    """纯 numpy 画一帧柱状频谱。levels 已归一化到 [0, 1]。"""
    frame = np.broadcast_to(bg, (height, width, 3)).copy()
    n = len(levels)
    bar_w = max(1, width // n)

    for i, lv in enumerate(levels):
        x0 = i * bar_w
        x1 = min(width, x0 + bar_w - gap)
        if x1 <= x0:
            continue
        h = int(lv * height)
        if h <= 0:
            continue
        # 柱体内部按高度取渐变色，顶部最亮
        ramp = (np.linspace(0.0, lv, h) * (len(lut) - 1)).astype(np.int32)
        frame[height - h:height, x0:x1] = lut[ramp][:, None, :][::-1]

    return frame


def render_video(
    audio: Audio,
    spec: Spectrogram,
    out_path: str | Path,
    fps: int = 30,
    width: int = 1280,
    height: int = 720,
    n_bars: int = 96,
    palette: str = "ember",
    smoothing: float = 0.6,
    crf: int = 20,
) -> Path:
    """渲染频谱视频并混入原音轨。

    smoothing 是时间方向的指数平滑系数（0 = 不平滑，柱子会抖得很难看；
    0.6 左右接近常见播放器的视觉手感）。
    """
    if not ffmpeg_available():
        raise RuntimeError("未找到 ffmpeg，请先安装：apt install ffmpeg / brew install ffmpeg")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmap = get_cmap(palette)
    lut = (np.asarray([cmap(x)[:3] for x in np.linspace(0, 1, 256)]) * 255).astype(np.uint8)
    bg = lut[0].astype(np.uint8)

    # dB → [0, 1]
    S = spec.S_db
    norm = np.clip((S - S.min()) / max(S.max() - S.min(), 1e-9), 0.0, 1.0)

    n_frames = int(audio.duration * fps)
    state = np.zeros(n_bars)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0",
        "-i", str(audio.path),
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(out_path),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None

    try:
        for k in range(n_frames):
            t = k / fps
            idx = min(int(np.searchsorted(spec.times, t)), norm.shape[1] - 1)
            target = _resample_rows(norm[:, idx], n_bars)
            state = smoothing * state + (1.0 - smoothing) * target
            proc.stdin.write(_draw_bars(state, width, height, lut, bg).tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="ignore") if proc.stderr else ""
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg 失败：\n{err}")

    return out_path
