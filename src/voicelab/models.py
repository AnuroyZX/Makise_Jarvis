from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class SynthesisRequest:
    text: str
    speaker_profile: str = "kurisu_amadeus"
    pitch_shift: int = 0
    index_rate: float = 0.75
    filter_radius: int = 3
    resample_sr: int = 0
    protect: float = 0.33


@dataclass(slots=True)
class SynthesisResult:
    audio_bytes: bytes
    sample_rate: int
    duration_sec: float
    provider: str
    vram_used_mb: float = 0.0


@dataclass(slots=True)
class VoicepackInfo:
    model_name: str
    pth_path: str
    index_path: str
    is_loaded: bool = False
    vram_mb: float = 0.0
