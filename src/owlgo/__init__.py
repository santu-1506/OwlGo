"""Owlgo: a DSA practice companion that hoots hints, not answers.

This package will hold the problem bank, the code runner client, the companion
prompt and spoiler guard, the training data pipeline and the evaluation tools.
See docs/spec.json for the full plan.
"""

# importlib.metadata reads information about installed packages.
from importlib.metadata import version

# Read the version from pyproject.toml (via the installed package metadata),
# so the version number only ever lives in one place.
__version__ = version("owlgo")
