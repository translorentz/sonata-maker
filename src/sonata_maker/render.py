"""External rendering steps: fluidsynth, pdftoppm, ImageMagick, ffmpeg."""

from __future__ import annotations

import re
from pathlib import Path

from sonata_maker.config import ToolPaths
from sonata_maker.errors import SonataGenerationError
from sonata_maker.output import banner, log, StepTimer
from sonata_maker.tools import local_arg, run_cmd


def midi_to_wav(
    tools: ToolPaths,
    midi_path: Path,
    wav_path: Path,
    soundfont: Path,
    sample_rate: int,
    *,
    fluidsynth_gain: float,
    verbose: bool,
) -> None:
    """Render a MIDI file to WAV using fluidsynth."""
    banner("[5/8] Rendering MIDI -> WAV (fluidsynth)")
    if not soundfont.exists():
        raise FileNotFoundError(f"SoundFont not found: {soundfont}")

    cmd = [
        tools.fluidsynth,
        "-ni",
        "-r", str(sample_rate),
        "-g", str(fluidsynth_gain),
        "-F", str(wav_path.resolve()),
        str(soundfont.resolve()),
        str(midi_path.resolve()),
    ]
    with StepTimer("fluidsynth render"):
        proc = run_cmd(cmd, verbose=verbose)

    if proc.returncode != 0:
        raise SonataGenerationError("fluidsynth failed (see output above).")
    log(f"[OK] Produced: {wav_path.name}")


def pdf_to_pngs(
    tools: ToolPaths,
    pdf_path: Path,
    png_prefix: Path,
    dpi: int,
    *,
    verbose: bool,
) -> list[Path]:
    """Convert a PDF to numbered PNG pages using pdftoppm."""
    banner("[6/8] Converting PDF -> PNG pages (pdftoppm)")
    cwd = pdf_path.parent

    pdf_arg = local_arg(pdf_path, cwd)
    prefix_arg = local_arg(png_prefix, cwd)

    cmd = [
        tools.pdftoppm,
        "-png",
        "-rx", str(dpi),
        "-ry", str(dpi),
        pdf_arg,
        prefix_arg,
    ]
    with StepTimer("pdftoppm convert"):
        proc = run_cmd(cmd, cwd=cwd, verbose=verbose)

    if proc.returncode != 0:
        raise SonataGenerationError("pdftoppm failed (see output above).")

    pattern = f"{Path(prefix_arg).name}-*.png"
    pages = sorted(
        cwd.glob(pattern),
        key=lambda p: int(re.findall(r"-(\d+)\.png$", p.name)[0]),
    )
    if not pages:
        raise FileNotFoundError(
            f"No PNG pages found matching {pattern} in {cwd}"
        )
    log(f"[OK] Produced {len(pages)} PNG pages (e.g., {pages[0].name})")
    return pages


def make_contact_sheet(
    tools: ToolPaths,
    page_pngs: list[Path],
    out_png: Path,
    montage_pages: int,
    *,
    verbose: bool,
) -> Path:
    """Create a horizontal contact sheet from score page PNGs."""
    banner("[7/8] Making contact sheet (ImageMagick)")
    cwd = out_png.parent
    chosen = page_pngs[: max(1, montage_pages)]

    chosen_args = [local_arg(p, cwd) for p in chosen]
    out_arg = local_arg(out_png, cwd)

    cmd = [tools.magick, *chosen_args, "+append", out_arg]
    with StepTimer("magick contact sheet"):
        proc = run_cmd(cmd, cwd=cwd, verbose=verbose)

    if proc.returncode != 0:
        raise SonataGenerationError("magick failed (see output above).")
    if not out_png.exists():
        raise FileNotFoundError(f"Contact sheet not created: {out_png}")

    log(f"[OK] Produced: {out_png.name}")
    return out_png


def make_mp4_stillimage(
    tools: ToolPaths,
    image_path: Path,
    wav_path: Path,
    mp4_path: Path,
    width: int,
    height: int,
    *,
    verbose: bool,
) -> None:
    """Create a still-image MP4 video from a score image and audio."""
    banner("[8/8] Making MP4 (ffmpeg)")
    cwd = mp4_path.parent

    img_arg = local_arg(image_path, cwd)
    wav_arg = local_arg(wav_path, cwd)
    mp4_arg = local_arg(mp4_path, cwd)

    vf = f"scale={width}:-2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"

    cmd = [
        tools.ffmpeg,
        "-y",
        "-loop", "1",
        "-i", img_arg,
        "-i", wav_arg,
        "-vf", vf,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        mp4_arg,
    ]
    with StepTimer("ffmpeg encode"):
        proc = run_cmd(cmd, cwd=cwd, verbose=verbose)

    if proc.returncode != 0:
        raise SonataGenerationError("ffmpeg failed (see output above).")
    log(f"[OK] Produced: {mp4_path.name}")
