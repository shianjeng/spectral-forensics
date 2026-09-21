"""spectral-forensics — 频谱检视与有损转码取证工具包。"""

from .audit import AuditResult, audit_file, audit_path
from .invert import (ComplexSpec, analyze, apply_mask, band_mask,
                     image_to_magnitude, mask_from_image, spectral_gate,
                     synthesize, write_wav)
from .io import Audio, load
from .reassign import ReassignedPoints, rasterize, reassign, sharpness
from .render import comparison, poster
from .transform import SpectroConfig, Spectrogram, compute

__version__ = "0.3.0"
__all__ = [
    "Audio", "load",
    "SpectroConfig", "Spectrogram", "compute",
    "poster", "comparison",
    "reassign", "rasterize", "sharpness", "ReassignedPoints",
    "audit_file", "audit_path", "AuditResult",
    "ComplexSpec", "analyze", "apply_mask", "band_mask", "spectral_gate",
    "mask_from_image", "synthesize", "image_to_magnitude", "write_wav",
]
