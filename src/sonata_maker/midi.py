"""MIDI velocity balancing between left and right hand channels."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import mido

from sonata_maker.output import log


def _channel_pitch_stats(midi_path: Path) -> Dict[int, Dict[str, int]]:
    """Gather note-on counts per channel, split by pitch threshold (middle C)."""
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


def guess_lh_rh_channels(
    midi_path: Path,
) -> Tuple[Optional[int], Optional[int]]:
    """Heuristically identify which MIDI channels are LH and RH.

    Uses pitch distribution: the channel with the most notes below middle C
    is guessed as LH; the channel with the most above is RH.
    """
    stats = _channel_pitch_stats(midi_path)
    if not stats:
        return None, None

    lh = max(
        stats.items(), key=lambda kv: (kv[1]["low"], kv[1]["total"])
    )[0]
    rh = max(
        stats.items(), key=lambda kv: (kv[1]["high"], kv[1]["total"])
    )[0]

    if rh == lh and len(stats) > 1:
        sorted_by_high = sorted(
            stats.items(),
            key=lambda kv: (kv[1]["high"], kv[1]["total"]),
            reverse=True,
        )
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
    """Scale note-on velocities per hand to balance LH/RH volume.

    Returns (lh_channel, rh_channel) as guessed.
    """
    lh_ch, rh_ch = guess_lh_rh_channels(in_midi)
    if verbose:
        log(
            f"[mix] Channel guess: LH={lh_ch}, RH={rh_ch} "
            f"(based on pitch distribution)"
        )

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
