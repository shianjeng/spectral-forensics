"""有损转码检测。

一个真实存在的需求：判断一个 FLAC 到底是不是从 mp3 转过来的。

原理：有损编码器为了省码率，会在某个频率以上把一切扔掉，留下一道
垂直的"悬崖"。把文件再转成 FLAC 之后，容器格式变了，但悬崖永远还在。

三个独立证据：
1. 截止频率 (cutoff)  —— 最高的、仍有实质能量的频率
2. 悬崖陡峭度 (steepness) —— 编码器是砖墙滤波，自然录音是缓坡
3. 强度立体声痕迹 (intensity stereo) —— 某个频率以上 L/R 合并成单声道

任何单一证据都会误判（老录音、原声吉他本来就没高频），三个一起看才稳。
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

AUDIO_SUFFIXES = {
    ".flac",
    ".wav",
    ".aiff",
    ".aif",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wv",
    ".ape",
    ".alac",
}

LOSSLESS_SUFFIXES = {".flac", ".wav", ".aiff", ".aif", ".wv", ".ape", ".alac"}

# 常见编码器的截止频率（kHz）→ 推测码率。
# 数值取自 LAME / Fraunhofer AAC 的默认低通设置，实测会有 ±0.5kHz 浮动。
CUTOFF_TABLE: list[tuple[float, str]] = [
    (11.0, "mp3 ~64 kbps 或 AAC ~48 kbps"),
    (13.0, "mp3 ~96 kbps"),
    (15.0, "mp3 ~112 kbps 或 AAC ~96 kbps"),
    (16.0, "mp3 ~128 kbps 或 AAC ~128 kbps"),
    (17.5, "mp3 ~160 kbps"),
    (19.0, "mp3 ~192 kbps 或 AAC ~192 kbps"),
    (20.0, "mp3 ~256–320 kbps 或 AAC ~256 kbps"),
]


@dataclass
class Probe:
    """ffprobe 给出的容器层信息。"""

    codec: str = "?"
    sample_rate: int = 0
    channels: int = 0
    bit_rate: int | None = None  # bps
    duration: float = 0.0


@dataclass
class AuditResult:
    path: str
    verdict: str  # clean / likely / suspect / lossy / unknown
    confidence: float  # 0–1
    cutoff_khz: float | None
    nyquist_khz: float
    steepness_db: float | None  # 悬崖处的跌落幅度
    stereo_cutoff_khz: float | None  # 强度立体声起点
    codec: str
    declared_kbps: float | None
    guess: str  # 推测的原始编码
    notes: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- 容器信息


def probe(path: Path) -> Probe:
    """调 ffprobe 拿编解码信息。失败就回落到 soundfile。"""
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                "-select_streams",
                "a:0",
                str(path),
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if out.returncode != 0:
            raise RuntimeError("ffprobe failed")
        data = json.loads(out.stdout or b"{}")
        st = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        br = st.get("bit_rate") or fmt.get("bit_rate")
        return Probe(
            codec=st.get("codec_name", "?"),
            sample_rate=int(st.get("sample_rate", 0) or 0),
            channels=int(st.get("channels", 0) or 0),
            bit_rate=int(br) if br else None,
            duration=float(fmt.get("duration", 0) or 0),
        )
    except (
        json.JSONDecodeError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ):
        try:
            info = sf.info(str(path))
            return Probe(
                codec=info.subtype or "?",
                sample_rate=info.samplerate,
                channels=info.channels,
                duration=info.duration,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return Probe()


# ---------------------------------------------------------------- 频谱统计


def long_term_spectrum(
    y: np.ndarray, sr: int, n_fft: int = 8192, percentile: float = 95.0
) -> tuple[np.ndarray, np.ndarray]:
    """长时谱：每个频点在时间轴上取高分位数。

    取分位数而不是平均，是因为整曲平均会被安静段落拖低，把真实的高频内容
    埋进噪声里；而取最大值又容易被单个瞬态毛刺带偏。95 分位是折中。
    """
    # center=False 很关键：默认的两端补零会制造阶跃，那是宽带的，
    # 首尾两帧整个频谱都被填满。信号越短帧数越少，这两帧在高分位里的
    # 权重就越大，短到一定程度会把截止判据整个淹掉。只分析真实存在的帧。
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=n_fft // 2, center=False)) ** 2
    ltas = np.percentile(S, percentile, axis=1)
    db = 10.0 * np.log10(ltas + 1e-20)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    return freqs, db


def _smooth(x: np.ndarray, width: int = 9) -> np.ndarray:
    k = np.ones(width) / width
    return np.convolve(x, k, mode="same")


def find_cutoff(
    freqs: np.ndarray, db: np.ndarray, drop_db: float = 50.0
) -> tuple[float | None, float | None]:
    """找截止频率和悬崖陡峭度。

    返回 (cutoff_hz, steepness_db)。steepness 定义为截止点往上 1 kHz 之内
    的额外跌落量——砖墙滤波在这段里会再掉 20 dB 以上，自然衰减则平缓得多。
    """
    db = _smooth(db)
    # 参考电平取中低频的峰值，避开直流和极高频
    band = (freqs >= 200) & (freqs <= 4000)
    if not band.any():
        return None, None
    ref = float(db[band].max())
    rel = db - ref

    above = np.where(rel > -drop_db)[0]
    if above.size == 0:
        return None, None
    idx = int(above[-1])
    f_c = float(freqs[idx])

    # 悬崖之上 1 kHz 处还掉了多少
    j = int(np.searchsorted(freqs, f_c + 1000.0))
    steepness = None
    if j < len(freqs):
        steepness = float(rel[idx] - rel[j])

    return f_c, steepness


def intensity_stereo_cutoff(
    path: Path, sr: int = 44100, n_fft: int = 4096
) -> float | None:
    """找强度立体声的起始频率。

    联合立体声在高频会把左右声道合并成一个单声道加权重，于是边信号
    (L-R)/2 的能量会在某个频率以上突然塌到接近零。这是有损编码的独立证据，
    和低通截止互相印证。
    """
    from .io import load_raw

    try:
        y, sr_actual = load_raw(path, sr=sr, mono=False)
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    if y.ndim != 2 or y.shape[0] < 2:
        return None

    mid = (y[0] + y[1]) / 2.0
    side = (y[0] - y[1]) / 2.0
    if np.max(np.abs(side)) < 1e-5:
        return None  # 本来就是假立体声，无从判断

    M = np.abs(librosa.stft(mid, n_fft=n_fft)) ** 2
    S = np.abs(librosa.stft(side, n_fft=n_fft)) ** 2
    ratio = 10.0 * np.log10(S.mean(axis=1) + 1e-20) - 10.0 * np.log10(
        M.mean(axis=1) + 1e-20
    )
    ratio = _smooth(ratio, 7)
    freqs = librosa.fft_frequencies(sr=sr_actual, n_fft=n_fft)

    # 在 4 kHz 以上找 side/mid 比值塌到 -40 dB 以下且不再回来的点
    start = int(np.searchsorted(freqs, 4000))
    collapsed = ratio < -40.0
    for i in range(start, len(freqs)):
        if collapsed[i:].all():
            return float(freqs[i])
    return None


def guess_source(cutoff_khz: float) -> str:
    """把截止频率映射到推测的原始编码。"""
    best, label = None, "未知有损编码"
    for f, name in CUTOFF_TABLE:
        d = abs(cutoff_khz - f)
        if best is None or d < best:
            best, label = d, name
    return label if best is not None and best <= 1.2 else "未知有损编码"


# ---------------------------------------------------------------- 主流程


def audit_file(
    path: str | Path,
    analysis_sr: int = 44100,
    max_seconds: float = 120.0,
    check_stereo: bool = True,
) -> AuditResult:
    """审计单个文件，给出是否为有损转码的判断。"""
    path = Path(path)
    info = probe(path)
    notes: list[str] = []

    from .io import load_raw

    y, sr = load_raw(path, sr=analysis_sr, mono=True, duration=max_seconds)
    nyq = sr / 2000.0  # kHz

    freqs, db = long_term_spectrum(y, sr)
    f_c, steep = find_cutoff(freqs, db)
    cutoff_khz = f_c / 1000.0 if f_c else None

    stereo_khz = None
    if check_stereo and info.channels and info.channels >= 2:
        s = intensity_stereo_cutoff(path, sr=analysis_sr)
        stereo_khz = s / 1000.0 if s else None

    is_lossless_container = path.suffix.lower() in LOSSLESS_SUFFIXES
    declared_kbps = info.bit_rate / 1000.0 if info.bit_rate else None

    # ---- 打分
    score = 0.0
    if cutoff_khz is not None:
        headroom = nyq - cutoff_khz
        if headroom > 1.2:  # 明显没画满整个频带
            score += 0.45
            if steep is not None and steep >= 20.0:
                score += 0.30  # 砖墙
                notes.append(f"截止处 1 kHz 内再跌 {steep:.0f} dB，呈砖墙特征")
            elif steep is not None:
                notes.append(f"截止处跌落仅 {steep:.0f} dB，更像自然衰减")
            # 落在编码器常用档位附近，额外加分
            if min(abs(cutoff_khz - f) for f, _ in CUTOFF_TABLE) <= 0.6:
                score += 0.15
        else:
            notes.append("频谱延伸到接近奈奎斯特频率，未见低通")

    if stereo_khz is not None:
        score += 0.25
        notes.append(f"{stereo_khz:.1f} kHz 以上边信号塌陷，疑似强度立体声")

    score = min(score, 1.0)

    # ---- 结论
    if not is_lossless_container:
        # 本来就是有损格式：只关心"虚标码率"（低码率转高码率）
        verdict = "lossy"
        if declared_kbps and cutoff_khz:
            implied = guess_source(cutoff_khz)
            notes.append(f"声明 {declared_kbps:.0f} kbps，频谱只支持 {implied}")
            if declared_kbps >= 256 and cutoff_khz < 18.0:
                verdict = "suspect"
                notes.append("高码率标称配低频谱上限，疑似低码率文件二次编码")
    elif score >= 0.70:
        verdict = "suspect"  # 低通 + 砖墙，通常还落在编码器常用档位上
    elif score >= 0.45:
        verdict = "likely"  # 只有低通，缺少砖墙或立体声佐证
    else:
        verdict = "clean"

    if (
        info.sample_rate
        and info.sample_rate > 48000
        and cutoff_khz
        and cutoff_khz < 22.0
    ):
        notes.append(
            f"容器标称 {info.sample_rate / 1000:.1f} kHz 采样率，"
            f"但实际内容止于 {cutoff_khz:.1f} kHz，疑似上采样"
        )

    return AuditResult(
        path=str(path),
        verdict=verdict,
        confidence=round(score, 2),
        cutoff_khz=round(cutoff_khz, 2) if cutoff_khz else None,
        nyquist_khz=round(nyq, 2),
        steepness_db=round(steep, 1) if steep is not None else None,
        stereo_cutoff_khz=round(stereo_khz, 2) if stereo_khz else None,
        codec=info.codec,
        declared_kbps=round(declared_kbps, 1) if declared_kbps else None,
        guess=guess_source(cutoff_khz) if cutoff_khz and verdict != "clean" else "—",
        notes=notes,
    )


def audit_path(root: str | Path, recursive: bool = True, **kwargs) -> list[AuditResult]:
    """审计一个文件或整个目录。"""
    root = Path(root)
    if root.is_file():
        return [audit_file(root, **kwargs)]

    pattern = "**/*" if recursive else "*"
    files = sorted(
        p
        for p in root.glob(pattern)
        if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES
    )
    results = []
    for p in files:
        try:
            results.append(audit_file(p, **kwargs))
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            # 坏文件不该中断整库扫描
            results.append(
                AuditResult(
                    path=str(p),
                    verdict="unknown",
                    confidence=0.0,
                    cutoff_khz=None,
                    nyquist_khz=0.0,
                    steepness_db=None,
                    stereo_cutoff_khz=None,
                    codec="?",
                    declared_kbps=None,
                    guess="—",
                    notes=[f"读取失败: {exc}"],
                )
            )
    return results
