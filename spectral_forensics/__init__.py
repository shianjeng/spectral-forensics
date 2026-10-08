"""spectral-forensics — 频谱检视与有损转码取证工具包。"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .audit import AuditResult, audit_file, audit_path
from .invert import (
    ComplexSpec,
    analyze,
    apply_mask,
    band_mask,
    image_to_magnitude,
    mask_from_image,
    spectral_gate,
    synthesize,
    write_wav,
)
from .io import Audio, load
from .reassign import ReassignedPoints, rasterize, reassign, sharpness
from .render import comparison, poster
from .transform import SpectroConfig, Spectrogram, compute

# 版本号只写在 pyproject.toml 里，这里从安装信息读取，免得两处不同步
# （0.4.1 就发生过：包是 0.4.1，`spf --version` 却报 0.4.0）。
try:
    __version__ = _version("spectral-forensics")
except PackageNotFoundError:  # 没安装、直接从源码目录导入
    __version__ = "0+unknown"
__all__ = [
    "Audio",
    "AuditResult",
    "ComplexSpec",
    "ReassignedPoints",
    "SpectroConfig",
    "Spectrogram",
    "analyze",
    "apply_mask",
    "audit_file",
    "audit_path",
    "band_mask",
    "comparison",
    "compute",
    "image_to_magnitude",
    "load",
    "mask_from_image",
    "poster",
    "rasterize",
    "reassign",
    "sharpness",
    "spectral_gate",
    "synthesize",
    "write_wav",
]
