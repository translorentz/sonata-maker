"""Tests for tool discovery and utility functions."""

import pytest

from sonata_maker.tools import validate_basename


class TestValidateBasename:
    def test_simple_name(self):
        assert validate_basename("sonata") == "sonata"

    def test_name_with_numbers(self):
        assert validate_basename("sonata_01") == "sonata_01"

    def test_name_with_dots_and_hyphens(self):
        assert validate_basename("my-sonata.v2") == "my-sonata.v2"

    def test_rejects_leading_dot(self):
        with pytest.raises(ValueError, match="start with"):
            validate_basename(".hidden")

    def test_rejects_forward_slash(self):
        with pytest.raises(ValueError, match="path separators"):
            validate_basename("foo/bar")

    def test_rejects_backslash(self):
        with pytest.raises(ValueError, match="path separators"):
            validate_basename("foo\\bar")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="unsupported characters"):
            validate_basename("my sonata")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            validate_basename("")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError):
            validate_basename("son@ta!")
