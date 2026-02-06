"""End-to-end orchestration: motif -> LilyPond -> PDF/MIDI -> WAV -> MP4."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from openai import OpenAI

from sonata_maker.config import RenderConfig, ToolPaths
from sonata_maker.errors import SonataGenerationError
from sonata_maker.generate import fix_sonata_lilypond, generate_sonata_lilypond
from sonata_maker.lilypond import compile_lilypond
from sonata_maker.midi import balance_midi_velocities
from sonata_maker.output import banner, log, StepTimer
from sonata_maker.render import (
    make_contact_sheet,
    make_mp4_stillimage,
    midi_to_wav,
    pdf_to_pngs,
)
from sonata_maker.tools import read_text, validate_basename, write_text


def build_outputs(
    motif_text: str,
    out_dir: Path,
    basename: str,
    title: str,
    soundfont: Path,
    tools: ToolPaths,
    cfg: RenderConfig,
    *,
    verbose: bool,
    lh_scale: float,
    rh_scale: float,
    fluidsynth_gain: float,
    no_midi_balance: bool,
) -> dict[str, Optional[Path]]:
    """Run the full generation and rendering pipeline.

    Returns a dict mapping output names to their file paths.
    """
    basename = validate_basename(basename)
    title = title.strip() if title.strip() else basename

    banner("[0/8] Setup")
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {out_dir.resolve()}")
    log(f"Output base:      {basename}")
    log(f"Score title:      {title}")
    log(f"SoundFont:        {soundfont.resolve()}")
    log(
        f"Tools: lilypond={tools.lilypond}, fluidsynth={tools.fluidsynth}, "
        f"pdftoppm={tools.pdftoppm}, magick={tools.magick}, "
        f"ffmpeg={tools.ffmpeg}"
    )
    log(
        f"MIDI mix:         {'OFF' if no_midi_balance else 'ON'} "
        f"(LH scale={lh_scale}, RH scale={rh_scale}), "
        f"fluidsynth gain={fluidsynth_gain}"
    )

    # -- OpenAI client --
    banner("[0.5/8] Initializing OpenAI client")
    with StepTimer("OpenAI client init"):
        client = OpenAI()

    # [1] Generate LilyPond
    ly_code = generate_sonata_lilypond(client, motif_text, title, cfg)
    ly_path = out_dir / f"{basename}.ly"
    banner("[1.5/8] Writing LilyPond file")
    with StepTimer(f"write {ly_path.name}"):
        write_text(ly_path, ly_code)
    log(f"[OK] Wrote: {ly_path.resolve()}")

    # [2] Compile LilyPond -> PDF + MIDI, with repair loop
    out_base = out_dir / basename
    pdf_path: Optional[Path] = None
    midi_raw: Optional[Path] = None

    for fix_attempt in range(cfg.max_compile_fix_attempts + 1):
        try:
            pdf_path, midi_raw = compile_lilypond(
                tools, ly_path, out_base, verbose=verbose
            )
            break
        except SonataGenerationError as e:
            log(
                f"[WARN] Compile attempt failed "
                f"({fix_attempt + 1}/{cfg.max_compile_fix_attempts + 1})."
            )
            cmd = [tools.lilypond, "-o", out_base.name, ly_path.name]
            cap = subprocess.run(
                cmd, cwd=str(out_dir), capture_output=True, text=True,
                check=False,
            )

            if fix_attempt >= cfg.max_compile_fix_attempts:
                raise SonataGenerationError(
                    f"{e}\n\nFinal LilyPond stderr:\n{cap.stderr}\n"
                ) from e

            fixed = fix_sonata_lilypond(
                client, read_text(ly_path), cmd, cap.stderr, title, cfg
            )
            banner("[X] Writing repaired LilyPond file and retrying compile")
            write_text(ly_path, fixed)

    assert pdf_path is not None and midi_raw is not None

    # [3] Create velocity-balanced MIDI for audio rendering
    banner("[3/8] Balancing MIDI velocities (LH/RH mix)")
    midi_mix = out_dir / f"{basename}_mix.midi"

    if no_midi_balance:
        log("[mix] Skipping MIDI balancing; using raw MIDI for audio.")
        midi_for_audio = midi_raw
    else:
        with StepTimer("midi velocity scaling"):
            lh_ch, rh_ch = balance_midi_velocities(
                midi_raw,
                midi_mix,
                left_scale=lh_scale,
                right_scale=rh_scale,
                verbose=verbose,
            )
        log(f"[OK] Wrote: {midi_mix.name} (LH ch={lh_ch}, RH ch={rh_ch})")
        midi_for_audio = midi_mix

    # [4] MIDI -> WAV
    wav_path = out_dir / f"{basename}.wav"
    midi_to_wav(
        tools,
        midi_for_audio,
        wav_path,
        soundfont,
        cfg.sample_rate,
        fluidsynth_gain=fluidsynth_gain,
        verbose=verbose,
    )

    # [5] PDF -> PNG pages
    png_prefix = out_dir / f"{basename}_score"
    pages = pdf_to_pngs(tools, pdf_path, png_prefix, cfg.dpi, verbose=verbose)

    # [6] Contact sheet
    sheet_path = out_dir / f"{basename}_contact.png"
    make_contact_sheet(
        tools, pages, sheet_path, cfg.montage_pages, verbose=verbose
    )

    # [7] MP4
    mp4_path = out_dir / f"{basename}.mp4"
    make_mp4_stillimage(
        tools,
        sheet_path,
        wav_path,
        mp4_path,
        cfg.video_width,
        cfg.video_height,
        verbose=verbose,
    )

    banner("[DONE] Finished")
    return {
        "lilypond": ly_path,
        "pdf": pdf_path,
        "midi_raw": midi_raw,
        "midi_mix": None if no_midi_balance else midi_mix,
        "midi_used_for_audio": midi_for_audio,
        "wav": wav_path,
        "mp4": mp4_path,
        "contact_sheet": sheet_path,
        "out_dir": out_dir,
    }
