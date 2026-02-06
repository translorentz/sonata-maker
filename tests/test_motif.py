"""Tests for motif parsing."""

from sonata_maker.motif import extract_key_and_time


class TestExtractKeyAndTime:
    def test_g_major_2_4(self):
        motif = r"\key g \major \time 2/4 g'8 d''8 b'8 a'8"
        key, time = extract_key_and_time(motif)
        assert key == "g major"
        assert time == "2/4"

    def test_c_minor_3_4(self):
        motif = r"\key c \minor \time 3/4 c'4 ees'4 g'4"
        key, time = extract_key_and_time(motif)
        assert key == "c minor"
        assert time == "3/4"

    def test_fis_major(self):
        motif = r"\key fis \major \time 4/4 fis'1"
        key, time = extract_key_and_time(motif)
        assert key == "f# major"
        assert time == "4/4"

    def test_bes_minor(self):
        motif = r"\key bes \minor \time 6/8 bes4."
        key, time = extract_key_and_time(motif)
        assert key == "bb minor"
        assert time == "6/8"

    def test_defaults_when_missing(self):
        motif = "c'4 d'4 e'4 f'4"
        key, time = extract_key_and_time(motif)
        assert key == "g major"
        assert time == "2/4"

    def test_key_only(self):
        motif = r"\key a \minor c'4 d'4"
        key, time = extract_key_and_time(motif)
        assert key == "a minor"
        assert time == "2/4"

    def test_time_only(self):
        motif = r"\time 5/4 c'4 d'4 e'4 f'4 g'4"
        key, time = extract_key_and_time(motif)
        assert key == "g major"
        assert time == "5/4"
