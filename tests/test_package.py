"""Smoke test: proves the package installs and imports, and that pytest is wired up."""

# The package under test.
import owlgo


def test_version_is_set():
    # __version__ comes from pyproject.toml, so it should be a non-empty string.
    assert isinstance(owlgo.__version__, str)
    assert owlgo.__version__ != ""
