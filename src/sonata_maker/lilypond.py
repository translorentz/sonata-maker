"""LilyPond source validation, header injection, and compilation."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Tuple

from sonata_maker.config import ToolPaths
from sonata_maker.errors import SonataGenerationError
from sonata_maker.output import banner, log, StepTimer
from sonata_maker.tools import run_cmd


def lilypond_escape_string(s: str) -> str:
    """Escape a string for use inside LilyPond double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def sanitize_model_output(text: str) -> str:
    """Strip markdown fences and whitespace from LLM-generated LilyPond."""
    t = text.strip()
    t = re.sub(r"^```(?:lilypond)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def validate_lilypond_source(src: str) -> None:
    """Check that LilyPond source meets structural requirements.

    Raises SonataGenerationError with all violations found.
    """
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
        raise SonataGenerationError(
            "LilyPond validation failed:\n- " + "\n- ".join(errors)
        )


def inject_or_update_header(src: str, *, title: str) -> str:
    r"""Ensure a \header block exists with the given title and tagline=##f.

    If a header exists, update/insert title & tagline.
    If not, insert a header right after the \version line.
    """
    title_esc = lilypond_escape_string(title)

    header_pat = re.compile(r"(\\header\s*\{)(.*?)(\})", re.DOTALL)
    m = header_pat.search(src)

    def ensure_field(body: str, field: str, value: str) -> str:
        field_pat = re.compile(
            rf"(^\s*{re.escape(field)}\s*=\s*.*$)", re.MULTILINE
        )
        replacement_line = f"  {field} = {value}"
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
    header_block = (
        f'\\header {{\n  title = "{title_esc}"\n  tagline = ##f\n}}\n\n'
    )
    if vm:
        insert_pos = vm.end()
        return src[:insert_pos] + "\n" + header_block + src[insert_pos:]
    return header_block + src


def compile_lilypond(
    tools: ToolPaths,
    ly_path: Path,
    out_base: Path,
    *,
    verbose: bool,
) -> Tuple[Path, Path]:
    """Compile a .ly file to PDF + MIDI, returning (pdf_path, midi_path)."""
    banner("[2/8] Compiling LilyPond -> PDF + MIDI")
    cwd = ly_path.parent
    out_base_local = out_base.name

    cmd = [tools.lilypond, "-o", out_base_local, ly_path.name]
    with StepTimer("lilypond compile"):
        proc = run_cmd(cmd, cwd=cwd, verbose=verbose)

    if proc.returncode != 0:
        cap = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, check=False
        )
        raise SonataGenerationError(
            f"LilyPond compilation failed.\nSTDERR:\n{cap.stderr}\n"
        )

    pdf = cwd / f"{out_base_local}.pdf"
    midi1 = cwd / f"{out_base_local}.midi"
    midi2 = cwd / f"{out_base_local}.mid"
    midi = midi1 if midi1.exists() else midi2

    if not pdf.exists():
        raise FileNotFoundError(f"Expected PDF not found: {pdf}")
    if not midi.exists():
        raise FileNotFoundError(
            f"Expected MIDI not found: {midi1} or {midi2}"
        )

    log(f"[OK] Produced: {pdf.name}, {midi.name}")
    return pdf, midi
