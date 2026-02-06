"""External tool discovery and subprocess execution helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from sonata_maker.config import ToolPaths
from sonata_maker.output import log


def _which_or_hint(name: str) -> str:
    """Locate a CLI tool on PATH or raise with a helpful message."""
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f"Required tool '{name}' not found on PATH.")
    return found


def discover_tool_paths(
    lilypond: Optional[str] = None,
    fluidsynth: Optional[str] = None,
    pdftoppm: Optional[str] = None,
    magick: Optional[str] = None,
    ffmpeg: Optional[str] = None,
) -> ToolPaths:
    """Resolve all external tool paths, falling back to PATH lookup."""
    return ToolPaths(
        lilypond=lilypond or _which_or_hint("lilypond"),
        fluidsynth=fluidsynth or _which_or_hint("fluidsynth"),
        pdftoppm=pdftoppm or _which_or_hint("pdftoppm"),
        magick=magick or _which_or_hint("magick"),
        ffmpeg=ffmpeg or _which_or_hint("ffmpeg"),
    )


def run_cmd(
    cmd: list[str],
    *,
    cwd: Optional[Path] = None,
    verbose: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run an external command, optionally streaming output."""
    if verbose:
        log(f"      $ {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print("      " + line.rstrip("\n"), flush=True)
        rc = proc.wait()
        return subprocess.CompletedProcess(cmd, rc, "", "")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


def local_arg(path: Path, cwd: Path) -> str:
    """Return a path relative to cwd if possible, else absolute."""
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return str(path.resolve())


def read_text(path: Path) -> str:
    """Read a text file as UTF-8."""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """Write a text file as UTF-8, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def validate_basename(name: str) -> str:
    """Validate an output basename (no path separators, no leading dot)."""
    if name.startswith("."):
        raise ValueError("Output base name must not start with '.'")
    if "/" in name or "\\" in name:
        raise ValueError("Output base name must not contain path separators.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("Output base name contains unsupported characters.")
    return name
