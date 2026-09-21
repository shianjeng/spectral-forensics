"""音频读取：解码 → 单声道化 → 重采样。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Audio:
    """一段已解码的单声道音频。"""

    y: np.ndarray          # 波形，float32，范围约 [-1, 1]
    sr: int                # 采样率 (Hz)
    path: Path

    @property
    def duration(self) -> float:
        """时长（秒）。"""
        return len(self.y) / self.sr

    @property
    def title(self) -> str:
        """用文件名当标题（去掉扩展名）。"""
        return self.path.stem


def _decode_via_ffmpeg(
    path: Path, sr: int, mono: bool, offset: float, duration: float | None
) -> tuple[NDArray[np.float32], int]:
    """soundfile/audioread 打不开时（常见于 m4a/alac），直接走 ffmpeg 管道。"""
    cmd = ["ffmpeg", "-v", "quiet", "-i", str(path)]
    if offset:
        cmd = ["ffmpeg", "-v", "quiet", "-ss", str(offset), "-i", str(path)]
    if duration:
        cmd += ["-t", str(duration)]
    channels = 1 if mono else 2
    cmd += ["-f", "f32le", "-ac", str(channels), "-ar", str(sr), "pipe:1"]

    out = subprocess.run(cmd, capture_output=True, check=False)
    if out.returncode != 0 or not out.stdout:
        raise RuntimeError(f"ffmpeg 解码失败: {path}")

    y: NDArray[np.float32] = np.frombuffer(out.stdout, dtype=np.float32)
    if not mono:
        y = y.reshape(-1, 2).T.astype(np.float32)
    return y.copy(), sr


def load_raw(
    path: str | Path,
    sr: int = 22050,
    mono: bool = True,
    offset: float = 0.0,
    duration: float | None = None,
) -> tuple[NDArray[np.float32], int]:
    """稳健解码：先试 librosa，失败再退到 ffmpeg。返回 (波形, 采样率)。"""
    path = Path(path)
    try:
        y, sr_actual = librosa.load(path, sr=sr, mono=mono,
                                    offset=offset, duration=duration)
        if y.size:
            return y.astype(np.float32), int(sr_actual)
    except (RuntimeError, ValueError, OSError):
        # m4a/alac 等格式在部分环境下会走到这里，随后尝试 ffmpeg 回退。
        ...
    return _decode_via_ffmpeg(path, sr, mono, offset, duration)


def load(path: str | Path, sr: int = 22050, offset: float = 0.0,
         duration: float | None = None) -> Audio:
    """读入音频文件。

    sr=22050 是默认选择：奈奎斯特频率 11025 Hz，已经覆盖绝大部分乐音内容
    （钢琴最高音 C8 基频 4186 Hz），同时把数据量砍掉一半。
    需要看镲片、齿音这类高频细节时传 sr=44100。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"找不到音频文件: {path}")

    y, sr_actual = load_raw(path, sr=sr, mono=True,
                            offset=offset, duration=duration)
    if y.size == 0:
        raise ValueError(f"音频为空（检查 offset/duration 是否超出时长）: {path}")

    return Audio(y=y.astype(np.float32), sr=int(sr_actual), path=path)


def estimate_tempo(audio: Audio) -> float:
    """估计 BPM，用于海报上的元信息标注。"""
    tempo, _ = librosa.beat.beat_track(y=audio.y, sr=audio.sr)
    return float(np.atleast_1d(tempo)[0])


def beat_times(audio: Audio) -> np.ndarray:
    """节拍点时刻（秒），给视频模式打节奏用。"""
    _, frames = librosa.beat.beat_track(y=audio.y, sr=audio.sr)
    return librosa.frames_to_time(frames, sr=audio.sr)
