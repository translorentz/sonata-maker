"""Tests for MIDI velocity balancing."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sonata_maker.midi import _channel_pitch_stats, guess_lh_rh_channels


def _make_mock_midi(notes: list[tuple[int, int, int]]):
    """Create a mock MidiFile with note_on messages.

    notes: list of (channel, pitch, velocity) tuples.
    """
    mock_midi = MagicMock()
    messages = []
    for ch, pitch, vel in notes:
        msg = MagicMock()
        msg.type = "note_on"
        msg.velocity = vel
        msg.note = pitch
        msg.channel = ch
        messages.append(msg)

    track = MagicMock()
    track.__iter__ = lambda self: iter(messages)
    mock_midi.tracks = [track]
    return mock_midi


class TestChannelPitchStats:
    @patch("sonata_maker.midi.mido.MidiFile")
    def test_basic_stats(self, mock_midifile):
        mock_midifile.return_value = _make_mock_midi([
            (0, 40, 80),   # low note, channel 0
            (0, 45, 70),   # low note, channel 0
            (1, 72, 90),   # high note, channel 1
            (1, 80, 85),   # high note, channel 1
        ])
        stats = _channel_pitch_stats(Path("dummy.midi"))
        assert stats[0]["low"] == 2
        assert stats[0]["high"] == 0
        assert stats[1]["low"] == 0
        assert stats[1]["high"] == 2

    @patch("sonata_maker.midi.mido.MidiFile")
    def test_zero_velocity_ignored(self, mock_midifile):
        mock_midifile.return_value = _make_mock_midi([
            (0, 40, 0),    # velocity 0 = note off
            (0, 45, 80),
        ])
        stats = _channel_pitch_stats(Path("dummy.midi"))
        assert stats[0]["total"] == 1

    @patch("sonata_maker.midi.mido.MidiFile")
    def test_empty_midi(self, mock_midifile):
        mock_midi = MagicMock()
        mock_midi.tracks = []
        mock_midifile.return_value = mock_midi
        stats = _channel_pitch_stats(Path("dummy.midi"))
        assert stats == {}


class TestGuessLhRhChannels:
    @patch("sonata_maker.midi._channel_pitch_stats")
    def test_clear_separation(self, mock_stats):
        mock_stats.return_value = {
            0: {"low": 100, "high": 5, "total": 105},
            1: {"low": 5, "high": 100, "total": 105},
        }
        lh, rh = guess_lh_rh_channels(Path("dummy.midi"))
        assert lh == 0
        assert rh == 1

    @patch("sonata_maker.midi._channel_pitch_stats")
    def test_empty_returns_none(self, mock_stats):
        mock_stats.return_value = {}
        lh, rh = guess_lh_rh_channels(Path("dummy.midi"))
        assert lh is None
        assert rh is None

    @patch("sonata_maker.midi._channel_pitch_stats")
    def test_single_channel_gets_both(self, mock_stats):
        mock_stats.return_value = {
            0: {"low": 50, "high": 50, "total": 100},
        }
        lh, rh = guess_lh_rh_channels(Path("dummy.midi"))
        # With only one channel, both LH and RH end up as the same
        assert lh == 0
        assert rh == 0
