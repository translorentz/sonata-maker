"""Configuration dataclasses for tool paths and render settings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolPaths:
    """Resolved absolute paths to required external CLI tools."""

    lilypond: str
    fluidsynth: str
    pdftoppm: str
    magick: str
    ffmpeg: str


@dataclass(frozen=True)
class RenderConfig:
    """Tunable parameters for the generation and rendering pipeline."""

    model: str = "gpt-5.2"
    reasoning_effort: str = "high"
    sample_rate: int = 44100
    dpi: int = 300
    video_width: int = 1920
    video_height: int = 1200
    montage_pages: int = 4
    max_generation_attempts: int = 2
    max_compile_fix_attempts: int = 2
