"""Tests for LilyPond source manipulation."""

import pytest

from sonata_maker.errors import SonataGenerationError
from sonata_maker.lilypond import (
    inject_or_update_header,
    lilypond_escape_string,
    sanitize_model_output,
    validate_lilypond_source,
)


class TestSanitizeModelOutput:
    def test_strips_markdown_fences(self):
        raw = '```lilypond\n\\version "2.24.0"\n```'
        assert sanitize_model_output(raw) == '\\version "2.24.0"'

    def test_strips_plain_fences(self):
        raw = '```\n\\version "2.24.0"\n```'
        assert sanitize_model_output(raw) == '\\version "2.24.0"'

    def test_strips_whitespace(self):
        raw = '  \n  \\version "2.24.0"  \n  '
        assert sanitize_model_output(raw) == '\\version "2.24.0"'

    def test_no_fences_passthrough(self):
        raw = '\\version "2.24.0"\n\\header {}'
        assert sanitize_model_output(raw) == raw


class TestLilypondEscapeString:
    def test_plain_string(self):
        assert lilypond_escape_string("Sonata in G") == "Sonata in G"

    def test_quotes(self):
        assert lilypond_escape_string('Say "hello"') == 'Say \\"hello\\"'

    def test_backslash(self):
        assert lilypond_escape_string("a\\b") == "a\\\\b"


class TestValidateLilypondSource:
    VALID_SRC = (
        '\\version "2.24.0"\n'
        "\\octaveCheck c'\n"
        "\\new PianoStaff { }\n"
        "\\midi { }\n"
        "\\layout { }\n"
    )

    def test_valid_source_passes(self):
        validate_lilypond_source(self.VALID_SRC)

    def test_rejects_relative(self):
        src = self.VALID_SRC + "\\relative c' { c d e f }"
        with pytest.raises(SonataGenerationError, match="relative"):
            validate_lilypond_source(src)

    def test_rejects_missing_version(self):
        src = "\\octaveCheck c'\n\\new PianoStaff { }\n\\midi { }\n\\layout { }"
        with pytest.raises(SonataGenerationError, match="version"):
            validate_lilypond_source(src)

    def test_rejects_missing_octave_check(self):
        src = '\\version "2.24.0"\n\\new PianoStaff { }\n\\midi { }\n\\layout { }'
        with pytest.raises(SonataGenerationError, match="octaveCheck"):
            validate_lilypond_source(src)

    def test_rejects_missing_piano_staff(self):
        src = '\\version "2.24.0"\n\\octaveCheck c\'\n\\midi { }\n\\layout { }'
        with pytest.raises(SonataGenerationError, match="PianoStaff"):
            validate_lilypond_source(src)

    def test_rejects_missing_midi(self):
        src = '\\version "2.24.0"\n\\octaveCheck c\'\n\\new PianoStaff { }\n\\layout { }'
        with pytest.raises(SonataGenerationError, match="midi"):
            validate_lilypond_source(src)

    def test_rejects_missing_layout(self):
        src = '\\version "2.24.0"\n\\octaveCheck c\'\n\\new PianoStaff { }\n\\midi { }'
        with pytest.raises(SonataGenerationError, match="layout"):
            validate_lilypond_source(src)

    def test_reports_multiple_errors(self):
        with pytest.raises(SonataGenerationError) as exc_info:
            validate_lilypond_source("\\relative c' { c d e f }")
        msg = str(exc_info.value)
        assert "relative" in msg
        assert "version" in msg
        assert "octaveCheck" in msg


class TestInjectOrUpdateHeader:
    def test_inserts_header_after_version(self):
        src = '\\version "2.24.0"\n\\new PianoStaff { }'
        result = inject_or_update_header(src, title="My Sonata")
        assert '\\header' in result
        assert 'title = "My Sonata"' in result
        assert 'tagline = ##f' in result

    def test_updates_existing_header(self):
        src = (
            '\\version "2.24.0"\n'
            '\\header {\n  title = "Old Title"\n  tagline = ##t\n}\n'
        )
        result = inject_or_update_header(src, title="New Title")
        assert 'title = "New Title"' in result
        assert 'tagline = ##f' in result
        assert "Old Title" not in result

    def test_adds_title_to_header_without_one(self):
        src = (
            '\\version "2.24.0"\n'
            '\\header {\n  composer = "Bach"\n}\n'
        )
        result = inject_or_update_header(src, title="Test")
        assert 'title = "Test"' in result
        assert 'composer = "Bach"' in result

    def test_escapes_special_characters(self):
        src = '\\version "2.24.0"\n'
        result = inject_or_update_header(src, title='Sonata "No. 1"')
        assert 'title = "Sonata \\"No. 1\\""' in result

    def test_no_version_prepends(self):
        src = "\\new PianoStaff { }"
        result = inject_or_update_header(src, title="Test")
        assert result.startswith("\\header")
