"""Command-line interface for sonata-maker."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

from sonata_maker.config import RenderConfig
from sonata_maker.output import log
from sonata_maker.pipeline import build_outputs
from sonata_maker.tools import discover_tool_paths, read_text, validate_basename


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(
        prog="sonata-maker",
        description=(
            "Generate a musically convincing piano sonata-form movement "
            "from a LilyPond motif."
        ),
    )
    p.add_argument(
        "motif",
        type=Path,
        help="Path to a LilyPond file (or snippet) containing the motif.",
    )
    p.add_argument(
        "-o", "--out",
        type=Path,
        default=Path("out_sonata"),
        help="Output directory (default: out_sonata).",
    )
    p.add_argument(
        "--name",
        type=str,
        default="sonata",
        help="Base filename for outputs (e.g. foo -> foo.ly/.pdf/.midi/.wav/.mp4).",
    )
    p.add_argument(
        "--title",
        type=str,
        default="",
        help="Score title placed in LilyPond \\header. Default: uses --name.",
    )
    p.add_argument(
        "--soundfont",
        type=Path,
        default=(
            Path(os.getenv("SOUNDFONT_PATH", ""))
            if os.getenv("SOUNDFONT_PATH")
            else None
        ),
        help="Path to a .sf2 SoundFont (or set SOUNDFONT_PATH env var).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Stream external tool output live.",
    )

    # MIDI balance controls
    mix = p.add_argument_group("MIDI balance")
    mix.add_argument(
        "--no-midi-balance",
        action="store_true",
        help="Disable MIDI velocity balancing step.",
    )
    mix.add_argument(
        "--lh-scale",
        type=float,
        default=0.78,
        help="Scale factor for LH velocities (smaller = softer LH).",
    )
    mix.add_argument(
        "--rh-scale",
        type=float,
        default=1.05,
        help="Scale factor for RH velocities (larger = louder RH).",
    )
    mix.add_argument(
        "--fluidsynth-gain",
        type=float,
        default=0.7,
        help="FluidSynth global gain (-g). Lower if clipping.",
    )

    # Tool path overrides
    tp = p.add_argument_group("tool overrides")
    tp.add_argument("--lilypond", type=str, default=None)
    tp.add_argument("--fluidsynth", type=str, default=None)
    tp.add_argument("--pdftoppm", type=str, default=None)
    tp.add_argument("--magick", type=str, default=None)
    tp.add_argument("--ffmpeg", type=str, default=None)

    # Render config overrides
    rc = p.add_argument_group("render config")
    rc.add_argument("--model", type=str, default="gpt-5.2")
    rc.add_argument(
        "--reasoning",
        type=str,
        default="high",
        choices=["none", "minimal", "low", "medium", "high"],
    )
    rc.add_argument("--dpi", type=int, default=300)
    rc.add_argument("--sample-rate", type=int, default=44100)
    rc.add_argument("--montage-pages", type=int, default=4)
    rc.add_argument("--video-width", type=int, default=1920)
    rc.add_argument("--video-height", type=int, default=1200)

    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point returning an exit code."""
    args = parse_args(argv)

    if args.soundfont is None:
        log("ERROR: --soundfont is required (or set SOUNDFONT_PATH).")
        return 2

    try:
        basename = validate_basename(args.name)
    except ValueError as e:
        log(f"ERROR: invalid --name: {e}")
        return 2

    if args.lh_scale <= 0 or args.rh_scale <= 0:
        log("ERROR: --lh-scale and --rh-scale must be > 0.")
        return 2

    if not (0.05 <= args.fluidsynth_gain <= 5.0):
        log("ERROR: --fluidsynth-gain is out of a sane range (try 0.3-1.0).")
        return 2

    motif_text = read_text(args.motif)

    try:
        tools = discover_tool_paths(
            lilypond=args.lilypond,
            fluidsynth=args.fluidsynth,
            pdftoppm=args.pdftoppm,
            magick=args.magick,
            ffmpeg=args.ffmpeg,
        )
    except FileNotFoundError as e:
        log(f"ERROR: {e}")
        return 2

    cfg = RenderConfig(
        model=args.model,
        reasoning_effort=args.reasoning,
        sample_rate=args.sample_rate,
        dpi=args.dpi,
        montage_pages=args.montage_pages,
        video_width=args.video_width,
        video_height=args.video_height,
    )

    try:
        outputs = build_outputs(
            motif_text=motif_text,
            out_dir=args.out,
            basename=basename,
            title=args.title,
            soundfont=args.soundfont,
            tools=tools,
            cfg=cfg,
            verbose=args.verbose,
            lh_scale=args.lh_scale,
            rh_scale=args.rh_scale,
            fluidsynth_gain=args.fluidsynth_gain,
            no_midi_balance=args.no_midi_balance,
        )
    except Exception as e:
        log(f"\nFAILED: {e}")
        return 1

    log("\nSuccess. Outputs:")
    log(f"  lilypond          -> {outputs['lilypond']}")
    log(f"  pdf               -> {outputs['pdf']}")
    log(f"  midi_raw          -> {outputs['midi_raw']}")
    if outputs.get("midi_mix"):
        log(f"  midi_mix          -> {outputs['midi_mix']}")
    log(f"  midi_for_wav      -> {outputs['midi_used_for_audio']}")
    log(f"  wav               -> {outputs['wav']}")
    log(f"  mp4               -> {outputs['mp4']}")
    log(f"  contact_sheet     -> {outputs['contact_sheet']}")
    return 0


def main_cli() -> None:
    """Wrapper for the console_scripts entry point."""
    raise SystemExit(main())
