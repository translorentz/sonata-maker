"""Tests for CLI argument parsing."""

from pathlib import Path

from sonata_maker.cli import parse_args


class TestParseArgs:
    def test_minimal_args(self):
        args = parse_args(["motif.ly"])
        assert args.motif == Path("motif.ly")
        assert args.out == Path("out_sonata")
        assert args.name == "sonata"
        assert args.title == ""
        assert args.verbose is False

    def test_all_main_args(self):
        args = parse_args([
            "my_motif.ly",
            "-o", "build",
            "--name", "sonata_01",
            "--title", "Sonata in G",
            "--verbose",
        ])
        assert args.motif == Path("my_motif.ly")
        assert args.out == Path("build")
        assert args.name == "sonata_01"
        assert args.title == "Sonata in G"
        assert args.verbose is True

    def test_midi_balance_defaults(self):
        args = parse_args(["motif.ly"])
        assert args.no_midi_balance is False
        assert args.lh_scale == 0.78
        assert args.rh_scale == 1.05
        assert args.fluidsynth_gain == 0.7

    def test_midi_balance_overrides(self):
        args = parse_args([
            "motif.ly",
            "--no-midi-balance",
            "--lh-scale", "0.5",
            "--rh-scale", "1.2",
            "--fluidsynth-gain", "0.4",
        ])
        assert args.no_midi_balance is True
        assert args.lh_scale == 0.5
        assert args.rh_scale == 1.2
        assert args.fluidsynth_gain == 0.4

    def test_render_config_defaults(self):
        args = parse_args(["motif.ly"])
        assert args.model == "gpt-5.2"
        assert args.reasoning == "high"
        assert args.dpi == 300
        assert args.sample_rate == 44100

    def test_tool_overrides(self):
        args = parse_args([
            "motif.ly",
            "--lilypond", "/opt/lilypond/bin/lilypond",
            "--ffmpeg", "/usr/local/bin/ffmpeg",
        ])
        assert args.lilypond == "/opt/lilypond/bin/lilypond"
        assert args.ffmpeg == "/usr/local/bin/ffmpeg"
        assert args.fluidsynth is None
