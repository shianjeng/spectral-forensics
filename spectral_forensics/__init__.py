"""spectral-forensics — 频谱检视与有损转码取证工具包。"""

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

__version__ = "0.4.0"
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
