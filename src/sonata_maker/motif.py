"""Motif parsing: extract key signature and time signature from LilyPond snippets."""

from __future__ import annotations

import re
from typing import Tuple

KEY_RE = re.compile(r"\\key\s+([a-g](?:is|es|#|b)?)\s+\\(major|minor)")
TIME_RE = re.compile(r"\\time\s+(\d+/\d+)")


def extract_key_and_time(motif: str) -> Tuple[str, str]:
    """Best-effort extraction of key and time signature from a LilyPond motif.

    Returns (key_desc, time_sig) with sensible defaults when not found.
    """
    key_match = KEY_RE.search(motif)
    time_match = TIME_RE.search(motif)

    if key_match:
        tonic, mode = key_match.group(1), key_match.group(2)
        key_desc = f"{tonic} {mode}".replace("is", "#").replace("es", "b")
    else:
        key_desc = "g major"

    time_sig = time_match.group(1) if time_match else "2/4"
    return key_desc, time_sig
