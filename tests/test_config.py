"""Tests for configuration dataclasses."""

from sonata_maker.config import RenderConfig, ToolPaths


class TestRenderConfig:
    def test_defaults(self):
        cfg = RenderConfig()
        assert cfg.model == "gpt-5.2"
        assert cfg.reasoning_effort == "high"
        assert cfg.sample_rate == 44100
        assert cfg.dpi == 300
        assert cfg.video_width == 1920
        assert cfg.video_height == 1200
        assert cfg.montage_pages == 4
        assert cfg.max_generation_attempts == 2
        assert cfg.max_compile_fix_attempts == 2

    def test_custom_values(self):
        cfg = RenderConfig(model="gpt-4o", dpi=150, sample_rate=48000)
        assert cfg.model == "gpt-4o"
        assert cfg.dpi == 150
        assert cfg.sample_rate == 48000

    def test_frozen(self):
        cfg = RenderConfig()
        try:
            cfg.model = "other"  # type: ignore[misc]
            assert False, "Should have raised"
        except AttributeError:
            pass


class TestToolPaths:
    def test_creation(self):
        tp = ToolPaths(
            lilypond="/usr/bin/lilypond",
            fluidsynth="/usr/bin/fluidsynth",
            pdftoppm="/usr/bin/pdftoppm",
            magick="/usr/bin/magick",
            ffmpeg="/usr/bin/ffmpeg",
        )
        assert tp.lilypond == "/usr/bin/lilypond"
        assert tp.ffmpeg == "/usr/bin/ffmpeg"

    def test_frozen(self):
        tp = ToolPaths(
            lilypond="a", fluidsynth="b", pdftoppm="c",
            magick="d", ffmpeg="e",
        )
        try:
            tp.lilypond = "other"  # type: ignore[misc]
            assert False, "Should have raised"
        except AttributeError:
            pass
