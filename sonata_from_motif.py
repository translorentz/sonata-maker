#!/usr/bin/env python3
"""
sonata_from_motif.py

End-to-end generator + renderer:
  Input:  a LilyPond motif file/snippet
  Output: 1) <name>.ly
          2) <name>.pdf
          3) <name>.midi (or .mid)          [raw LilyPond MIDI]
          4) <name>_mix.midi                [velocity-balanced MIDI for rendering]
          5) <name>.wav                     [rendered from the balanced MIDI]
          6) <name>.mp4                     [still-image video with audio]
          + intermediate PNG page renders: <name>_score-1.png, ...

External CLI tools required on PATH:
  - lilypond
  - fluidsynth
  - pdftoppm   (poppler)
  - magick     (ImageMagick)
  - ffmpeg

Python dependencies:
  pip install openai mido

Environment:
  export OPENAI_API_KEY="..."
Optional:
  export SOUNDFONT_PATH="/path/to/soundfont.sf2"

Examples:
  python3 sonata_from_motif.py motif.ly -o build_out --name sonata_01 --title "Sonata in G, Op. X" --verbose
  python3 sonata_from_motif.py motif.ly -o build_out --name sonata_01 --lh-scale 0.75 --rh-scale 1.08
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from openai import OpenAI
import mido


# ----------------------------
# Prompt: ensure the result is genuinely musical (not just “scales & arpeggios”)
# ----------------------------

SYSTEM_PROMPT = r"""
You are an expert classical/early-romantic composer, pianist-composer, and LilyPond engraver.

You must output ONLY valid LilyPond source code (no Markdown fences, no prose outside LilyPond comments).
The output MUST compile in LilyPond 2.24.x.

INTERNAL PLANNING:
- Plan internally before writing notes. Do not print your planning; output only the final LilyPond code.

HARD ENGRAVING CONSTRAINTS (non-negotiable):
- ABSOLUTE pitch mode ONLY. DO NOT use \relative anywhere.
- Insert \octaveCheck at structural points:
  - at the start of each big section (Intro, Exposition, Development, Recap, Coda)
  - after any large registral leap or rewrite-prone hotspot
- Use a PianoStaff with two staves labeled clearly:
  - RH staff: Staff.instrumentName = "Piano (RH)" and shortInstrumentName = "RH"
  - LH staff: Staff.instrumentName = "Piano (LH)" and shortInstrumentName = "LH"
  - Use midiInstrument = "acoustic grand" for both staves.
- Idiomatic range (working guideline, not a cage):
  - RH typically c' to c''''; LH typically E,, to g''.
- Avoid impossible hand stretches; prefer broken-chord figuration if wide.
- Dynamics MUST be attached to an event (note/rest) or a skip with duration (e.g., s2\p).
  Never output a bare \p/\mf/\f/etc on its own line.

SONATA-FORM COMPOSITION RUBRIC (high-level musicality > mechanical correctness)

A) FORM & PROPORTION
- Output a sonata-form first movement for solo piano.
- Overall size: roughly 180–260 measures in the given meter (or comparable musical duration).
- Exposition should be repeated (volta repeat is fine).
- Development must be substantial and argumentative (not a short interlude).
- Coda should feel earned and rhetorically necessary.

B) INTRO (if present) MUST NOT BE LETHARGIC
Choose ONE:
1) NO slow introduction: go straight into Allegro with energy.
2) A short intro (max 8–14 bars) that is ACTIVE, not sluggish:
   - steady pulse, clear harmonic direction, rhetorical gestures, and/or motivic foreshadowing.
   - if tempo marking is slower, compensate with texture/activity (e.g., suspensions, inner motion, imitation).
Avoid long static chords. Avoid “dead air.”

C) THEMATIC CONTRAST (P vs S)
- The motif must be audibly present early in P and remain the generative DNA throughout.
- P: energetic/public rhetoric; clear tonal anchoring; a strong phrase type (sentence/period).
- S: clearly contrasting character (cantabile/lyrical or intimate), with:
  - different surface rhythm than P
  - different accompaniment texture than P
  - a distinct registral identity
- Do NOT simply transpose P to form S. S must feel like a different idea that shares DNA.

D) TEXTURE DIVERSITY REQUIREMENTS (this is critical)
The movement must employ at least 6 distinct textures across sections, chosen from:
1) melody + Alberti or broken-chord accompaniment
2) two-voice contrapuntal writing (invention-like) with imitation
3) chorale/homophonic chordal blocks with inner-voice motion
4) accompaniment in offbeat chords or syncopation (light, dancing)
5) layered texture: melody + inner counterline + bass (3-part implication)
6) tremolo/rolling figure used sparingly for crescendo/arrival (not everywhere)
7) octave-based brilliance (broken octaves, repeated notes) used as climax rhetoric
8) pedal-point texture (dominant pedal in retransition, tonic pedal in coda)

You must NOT rely on a single texture for more than ~16 bars at a time without a meaningful change.

E) “ANTI-ETUDE” GUARDRAILS (no endless scales/arpeggios)
- Scale runs and arpeggio runs are allowed only when they serve a PURPOSE:
  (cadential drive, sequence intensification, registral climax, retransition lock, or coda brilliance).
- Avoid continuous two-hand scale/arpeggio patterns for long stretches.
Rule of thumb: do not exceed 2 consecutive bars of uninterrupted scalar/arpeggiated figuration
without (i) thematic material, (ii) contrapuntal interaction, (iii) harmonic event/suspension, or (iv) textural shift.
- At least half of the development must NOT be built from simple scale/arpeggio passagework.

F) HARMONY / VOICE LEADING (avoid “blocky diatonic exercise”)
- Use inversions shaping bass lines, suspensions/appoggiaturas, applied dominants, and occasional mixture.
- Include at least one flat-side color region (e.g., bVI / bII6 / mixture) in the development in a plausible way.
- Ensure cadences are rhetorically clear (HC, IAC/PAC) with proper preparation.

G) DEVELOPMENT (must be transformative)
Must include:
- inversion OR augmentation at least once (explicit, audible)
- imitation/canon between hands at least once
Plus at least 2 additional processes from:
- recombination of P and S fragments
- chromatic voice-leading sequence
- registral narrative (gradual expansion to climax)
- texture metamorphosis (e.g., cantabile theme becomes fugato, or chordal becomes scherzando)

H) RECAP & CODA
- Recap resolves tonal conflict: S and C in tonic.
- TR rewritten to avoid modulating away (but keep energy).
- Coda is not perfunctory: can be a mini-development in tonic and/or a rhetorical apotheosis.

NOTATION / MUSICALITY
- Use slurs for cantabile; use articulation sparingly but meaningfully.
- Add occasional pedaling (\sustainOn/\sustainOff) in lyrical areas and major cadences.
- Keep marks clean: \mark only at major divisions.

OUTPUT REQUIREMENTS
- Include \version "2.24.0"
- Include \header with title and tagline = ##f
- Include \layout and \midi blocks.
- Output ONLY LilyPond code.
"""

USER_PROMPT_TEMPLATE = r"""
Compose a complete sonata-form first movement for solo piano in LilyPond.

You must follow the rubric precisely; especially:
- Intro must not be lethargic (or omit it).
- Texture must be varied (>= 6 distinct textures over the movement).
- Avoid long stretches that are only scales/arpeggios; ensure musical argument.

MOTIF (LilyPond snippet):
{motif}

Context hints to respect:
- Key: {key_desc}
- Time signature: {time_sig}

Title to place in the score header (exact text):
{title}

Reminder constraints:
- LilyPond 2.24.0
- Absolute pitch only (no \relative).
- \octaveCheck at section starts.
- Exposition repeated.
- Development: inversion or augmentation at least once AND imitation at least once.
- Output ONLY LilyPond source code.
"""

FIX_PROMPT_TEMPLATE = r"""
The following LilyPond file failed to compile.

Compiler command:
{cmd}

Compiler stderr (most relevant excerpt):
{stderr}

Please rewrite the ENTIRE LilyPond file so that it compiles in LilyPond 2.24.0.
Preserve the musical goals and constraints (absolute pitch only, octaveChecks, sonata form, texture diversity,
anti-etude guardrails, etc.).
Return ONLY the corrected LilyPond source code.

BROKEN FILE:
{code}
"""


# ----------------------------
# Logging helpers
# ----------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def banner(msg: str) -> None:
    log("\n" + "=" * 72)
    log(msg)
    log("=" * 72)


class StepTimer:
    def __init__(self, label: str) -> None:
        self.label = label
        self.t0 = 0.0

    def __enter__(self) -> "StepTimer":
        self.t0 = time.perf_counter()
        log(f"[..] {self.label}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        dt = time.perf_counter() - self.t0
        if exc is None:
            log(f"[OK] {self.label} ({dt:.2f}s)")
        else:
            log(f"[!!] {self.label} failed after {dt:.2f}s")


# ----------------------------
# Settings / utilities
# ----------------------------

@dataclass(frozen=True)
class ToolPaths:
    lilypond: str
    fluidsynth: str
    pdftoppm: str
    magick: str
    ffmpeg: str


@dataclass(frozen=True)
class RenderConfig:
    model: str = "gpt-5.1"
    reasoning_effort: str = "high"
    sample_rate: int = 44100
    dpi: int = 300
    video_width: int = 1920
    video_height: int = 1200
    montage_pages: int = 4
    max_generation_attempts: int = 2
    max_compile_fix_attempts: int = 2


class SonataGenerationError(RuntimeError):
    pass


def _which_or_hint(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f"Required tool '{name}' not found on PATH.")
    return found


def discover_tool_paths(
    lilypond: Optional[str],
    fluidsynth: Optional[str],
    pdftoppm: Optional[str],
    magick: Optional[str],
    ffmpeg: Optional[str],
) -> ToolPaths:
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
) -> subprocess.CompletedProcess:
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
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return str(path.resolve())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def validate_basename(name: str) -> str:
    if name.startswith("."):
        raise ValueError("Output base name must not start with '.'")
    if "/" in name or "\\" in name:
        raise ValueError("Output base name must not contain path separators.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("Output base name contains unsupported characters.")
    return name


def lilypond_escape_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def inject_or_update_header(src: str, *, title: str) -> str:
    """
    Ensure there is a \\header block and that it contains title="<title>" and tagline=##f.
    If a header exists, update/insert title & tagline.
    If not, insert a header right after \\version line.
    """
    title_esc = lilypond_escape_string(title)

    header_pat = re.compile(r"(\\header\s*\{)(.*?)(\})", re.DOTALL)
    m = header_pat.search(src)

    def ensure_field(body: str, field: str, value: str) -> str:
        field_pat = re.compile(rf"(^\s*{re.escape(field)}\s*=\s*.*$)", re.MULTILINE)
        replacement_line = f'  {field} = {value}'
        if field_pat.search(body):
            return field_pat.sub(replacement_line, body, count=1)
        return replacement_line + "\n" + body.lstrip("\n")

    if m:
        start, body, end = m.group(1), m.group(2), m.group(3)
        body2 = ensure_field(body, "title", f'"{title_esc}"')
        body2 = ensure_field(body2, "tagline", "##f")
        new_header = start + body2 + end
        return src[: m.start()] + new_header + src[m.end() :]

    version_pat = re.compile(r'(\\version\s+"[^"]+"\s*)')
    vm = version_pat.search(src)
    header_block = f'\\header {{\n  title = "{title_esc}"\n  tagline = ##f\n}}\n\n'
    if vm:
        insert_pos = vm.end()
        return src[:insert_pos] + "\n" + header_block + src[insert_pos:]
    return header_block + src


# ----------------------------
# Motif parsing (best-effort)
# ----------------------------

KEY_RE = re.compile(r"\\key\s+([a-g](?:is|es|#|b)?)\s+\\(major|minor)")
TIME_RE = re.compile(r"\\time\s+(\d+/\d+)")


def extract_key_and_time(motif: str) -> Tuple[str, str]:
    key_match = KEY_RE.search(motif)
    time_match = TIME_RE.search(motif)

    if key_match:
        tonic, mode = key_match.group(1), key_match.group(2)
        key_desc = f"{tonic} {mode}".replace("is", "#").replace("es", "b")
    else:
        key_desc = "g major"

    time_sig = time_match.group(1) if time_match else "2/4"
    return key_desc, time_sig


# ----------------------------
# LilyPond validation helpers
# ----------------------------

def sanitize_model_output(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```(?:lilypond)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def validate_lilypond_source(src: str) -> None:
    errors: list[str] = []
    if "\\relative" in src:
        errors.append("Forbidden: found \\relative (must use absolute pitches).")
    if "\\version" not in src:
        errors.append("Missing \\version declaration.")
    if "\\octaveCheck" not in src:
        errors.append("Missing \\octaveCheck anchors.")
    if "\\new PianoStaff" not in src:
        errors.append("Missing \\new PianoStaff.")
    if "\\midi" not in src:
        errors.append("Missing \\midi block.")
    if "\\layout" not in src:
        errors.append("Missing \\layout block.")
    if errors:
        raise SonataGenerationError("LilyPond validation failed:\n- " + "\n- ".join(errors))


# ----------------------------
# OpenAI generation / repair (Responses API)
# ----------------------------

def generate_sonata_lilypond(client: OpenAI, motif_text: str, title: str, cfg: RenderConfig) -> str:
    key_desc, time_sig = extract_key_and_time(motif_text)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        motif=motif_text.strip(),
        key_desc=key_desc,
        time_sig=time_sig,
        title=title.strip(),
    )

    last_err: Optional[Exception] = None
    for attempt in range(1, cfg.max_generation_attempts + 1):
        banner(f"[1/8] Generating LilyPond sonata with {cfg.model} (attempt {attempt})")
        try:
            with StepTimer("OpenAI request (may take a while)"):
                # Responses API + reasoning.effort per current docs. :contentReference[oaicite:1]{index=1}
                resp = client.responses.create(
                    model=cfg.model,
                    reasoning={"effort": cfg.reasoning_effort},
                    input=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            ly = sanitize_model_output(resp.output_text)
            ly = inject_or_update_header(ly, title=title)
            validate_lilypond_source(ly)
            return ly
        except Exception as e:
            last_err = e
            log(f"[WARN] Generation attempt {attempt} failed: {e}")

    raise SonataGenerationError(f"Failed to generate valid LilyPond. Last error: {last_err}")


def fix_sonata_lilypond(
    client: OpenAI,
    broken_code: str,
    lilypond_cmd: list[str],
    lilypond_stderr: str,
    title: str,
    cfg: RenderConfig,
) -> str:
    excerpt = lilypond_stderr.strip()
    if len(excerpt) > 4000:
        excerpt = excerpt[-4000:]

    fix_prompt = FIX_PROMPT_TEMPLATE.format(
        cmd=" ".join(lilypond_cmd),
        stderr=excerpt,
        code=broken_code,
    )

    banner("[X] LilyPond failed; asking model to repair the full file")
    with StepTimer("OpenAI repair request (may take a while)"):
        resp = client.responses.create(
            model=cfg.model,
            reasoning={"effort": cfg.reasoning_effort},
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": fix_prompt},
            ],
        )

    ly = sanitize_model_output(resp.output_text)
    ly = inject_or_update_header(ly, title=title)
    validate_lilypond_source(ly)
    return ly


# ----------------------------
# MIDI balance (LH too loud fix)
# ----------------------------

def _channel_pitch_stats(midi_path: Path) -> Dict[int, Dict[str, int]]:
    mid = mido.MidiFile(midi_path)
    stats: Dict[int, Dict[str, int]] = {}
    for track in mid.tracks:
        for msg in track:
            if msg.type == "note_on" and msg.velocity > 0:
                ch = getattr(msg, "channel", 0)
                if ch not in stats:
                    stats[ch] = {"low": 0, "high": 0, "total": 0}
                if msg.note < 60:
                    stats[ch]["low"] += 1
                else:
                    stats[ch]["high"] += 1
                stats[ch]["total"] += 1
    return stats


def guess_lh_rh_channels(midi_path: Path) -> Tuple[Optional[int], Optional[int]]:
    stats = _channel_pitch_stats(midi_path)
    if not stats:
        return None, None

    lh = max(stats.items(), key=lambda kv: (kv[1]["low"], kv[1]["total"]))[0]
    rh = max(stats.items(), key=lambda kv: (kv[1]["high"], kv[1]["total"]))[0]

    if rh == lh and len(stats) > 1:
        sorted_by_high = sorted(stats.items(), key=lambda kv: (kv[1]["high"], kv[1]["total"]), reverse=True)
        for ch, _ in sorted_by_high:
            if ch != lh:
                rh = ch
                break

    return lh, rh


def balance_midi_velocities(
    in_midi: Path,
    out_midi: Path,
    *,
    left_scale: float,
    right_scale: float,
    verbose: bool,
) -> Tuple[Optional[int], Optional[int]]:
    lh_ch, rh_ch = guess_lh_rh_channels(in_midi)
    if verbose:
        log(f"[mix] Channel guess: LH={lh_ch}, RH={rh_ch} (based on pitch distribution)")

    mid = mido.MidiFile(in_midi)
    out = mido.MidiFile(ticks_per_beat=mid.ticks_per_beat)

    for track in mid.tracks:
        new_track = mido.MidiTrack()
        for msg in track:
            if msg.type == "note_on" and msg.velocity > 0:
                ch = getattr(msg, "channel", None)
                if ch is not None and lh_ch is not None and ch == lh_ch:
                    v = int(round(msg.velocity * left_scale))
                elif ch is not None and rh_ch is not None and ch == rh_ch:
                    v = int(round(msg.velocity * right_scale))
                else:
                    v = msg.velocity

                v = max(1, min(127, v))
                new_track.append(msg.copy(velocity=v))
            else:
                new_track.append(msg.copy())
        out.tracks.append(new_track)

    out.save(out_midi)
    return lh_ch, rh_ch


# ----------------------------
# Rendering pipeline
# ----------------------------

def compile_lilypond(
    tools: ToolPaths,
    ly_path: Path,
    out_base: Path,
    *,
    verbose: bool,
) -> Tuple[Path, Path]:
    banner("[2/8] Compiling LilyPond → PDF + MIDI")
    cwd = ly_path.parent
    out_base_local = out_base.name

    cmd = [tools.lilypond, "-o", out_base_local, ly_path.name]
    with StepTimer("lilypond compile"):
        proc = run_cmd(cmd, cwd=cwd, verbose=verbose)

    if proc.returncode != 0:
        cap = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
        raise SonataGenerationError(f"LilyPond compilation failed.\nSTDERR:\n{cap.stderr}\n")

    pdf = cwd / f"{out_base_local}.pdf"
    midi1 = cwd / f"{out_base_local}.midi"
    midi2 = cwd / f"{out_base_local}.mid"
    midi = midi1 if midi1.exists() else midi2

    if not pdf.exists():
        raise FileNotFoundError(f"Expected PDF not found: {pdf}")
    if not midi.exists():
        raise FileNotFoundError(f"Expected MIDI not found: {midi1} or {midi2}")

    log(f"[OK] Produced: {pdf.name}, {midi.name}")
    return pdf, midi


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
    banner("[5/8] Rendering MIDI → WAV (fluidsynth)")
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
    banner("[6/8] Converting PDF → PNG pages (pdftoppm)")
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
        raise FileNotFoundError(f"No PNG pages found matching {pattern} in {cwd}")
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


# ----------------------------
# Orchestration
# ----------------------------

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
    basename = validate_basename(basename)
    title = title.strip() if title.strip() else basename

    banner("[0/8] Setup")
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {out_dir.resolve()}")
    log(f"Output base:      {basename}")
    log(f"Score title:      {title}")
    log(f"SoundFont:        {soundfont.resolve()}")
    log(f"Tools: lilypond={tools.lilypond}, fluidsynth={tools.fluidsynth}, pdftoppm={tools.pdftoppm}, magick={tools.magick}, ffmpeg={tools.ffmpeg}")
    log(f"MIDI mix:         {'OFF' if no_midi_balance else 'ON'} (LH scale={lh_scale}, RH scale={rh_scale}), fluidsynth gain={fluidsynth_gain}")

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

    # [2] Compile LilyPond → PDF + MIDI, with repair loop
    out_base = out_dir / basename
    pdf_path: Optional[Path] = None
    midi_raw: Optional[Path] = None

    for fix_attempt in range(cfg.max_compile_fix_attempts + 1):
        try:
            pdf_path, midi_raw = compile_lilypond(tools, ly_path, out_base, verbose=verbose)
            break
        except SonataGenerationError as e:
            log(f"[WARN] Compile attempt failed ({fix_attempt + 1}/{cfg.max_compile_fix_attempts + 1}).")
            cmd = [tools.lilypond, "-o", out_base.name, ly_path.name]
            cap = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True)

            if fix_attempt >= cfg.max_compile_fix_attempts:
                raise SonataGenerationError(f"{e}\n\nFinal LilyPond stderr:\n{cap.stderr}\n") from e

            fixed = fix_sonata_lilypond(client, read_text(ly_path), cmd, cap.stderr, title, cfg)
            banner("[X] Writing repaired LilyPond file and retrying compile")
            write_text(ly_path, fixed)

    assert pdf_path is not None and midi_raw is not None

    # [3] Create velocity-balanced MIDI for audio rendering (optional)
    banner("[3/8] Balancing MIDI velocities (LH/RH mix)")
    midi_mix = out_dir / f"{basename}_mix.midi"

    if no_midi_balance:
        log("[mix] Skipping MIDI balancing; using raw MIDI for audio.")
        midi_for_audio = midi_raw
        lh_ch = rh_ch = None
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

    # [4] MIDI → WAV
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

    # [5] PDF → PNG pages
    png_prefix = out_dir / f"{basename}_score"
    pages = pdf_to_pngs(tools, pdf_path, png_prefix, cfg.dpi, verbose=verbose)

    # [6] Contact sheet
    sheet_path = out_dir / f"{basename}_contact.png"
    make_contact_sheet(tools, pages, sheet_path, cfg.montage_pages, verbose=verbose)

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


# ----------------------------
# CLI
# ----------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a musically convincing piano sonata-form movement from a LilyPond motif.")
    p.add_argument("motif", type=Path, help="Path to a LilyPond file (or snippet) containing the motif.")
    p.add_argument("-o", "--out", type=Path, default=Path("out_sonata"), help="Output directory.")
    p.add_argument("--name", type=str, default="sonata", help="Base filename for outputs (foo -> foo.ly/pdf/midi/wav/mp4).")
    p.add_argument("--title", type=str, default="", help="Score title placed in LilyPond \\header. Default: uses --name.")
    p.add_argument(
        "--soundfont",
        type=Path,
        default=Path(os.getenv("SOUNDFONT_PATH", "")) if os.getenv("SOUNDFONT_PATH") else None,
        help="Path to a .sf2 SoundFont (or set SOUNDFONT_PATH).",
    )
    p.add_argument("--verbose", action="store_true", help="Stream external tool output live.")

    # MIDI balance controls
    p.add_argument("--no-midi-balance", action="store_true", help="Disable MIDI velocity balancing step.")
    p.add_argument("--lh-scale", type=float, default=0.78, help="Scale factor for LH note_on velocities (smaller = softer LH).")
    p.add_argument("--rh-scale", type=float, default=1.05, help="Scale factor for RH note_on velocities (bigger = louder RH).")
    p.add_argument("--fluidsynth-gain", type=float, default=0.7, help="FluidSynth global gain (-g). Lower if clipping / too loud.")

    # Tool overrides (optional)
    p.add_argument("--lilypond", type=str, default=None)
    p.add_argument("--fluidsynth", type=str, default=None)
    p.add_argument("--pdftoppm", type=str, default=None)
    p.add_argument("--magick", type=str, default=None)
    p.add_argument("--ffmpeg", type=str, default=None)

    # Render config overrides
    p.add_argument("--model", type=str, default="gpt-5.1")
    p.add_argument("--reasoning", type=str, default="high", choices=["none", "minimal", "low", "medium", "high"])
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--sample-rate", type=int, default=44100)
    p.add_argument("--montage-pages", type=int, default=4)
    p.add_argument("--video-width", type=int, default=1920)
    p.add_argument("--video-height", type=int, default=1200)
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
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
        log("ERROR: --fluidsynth-gain is out of a sane range (try 0.3–1.0).")
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


if __name__ == "__main__":
    raise SystemExit(main())
