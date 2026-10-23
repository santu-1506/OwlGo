"""The Help Dial: how much help each level allows (docs/spec.json -> help_dial)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpLevel:
    level: int
    name: str
    # The one-line rule the model sees in the context block.
    rule: str


HELP_LEVELS = {
    0: HelpLevel(
        0,
        "rubber_duck",
        "Only ask questions and reflect back what the user said. "
        "No hints about the technique, the data structure or where the bug is.",
    ),
    1: HelpLevel(
        1,
        "nudge",
        "One question or observation that points where to look. "
        "Don't name the algorithm, the data structure or the fix.",
    ),
    2: HelpLevel(
        2,
        "hint",
        "You may name the general idea or data structure, or point at the part of the code "
        "with the bug. Don't explain it step by step or state the fix.",
    ),
    3: HelpLevel(
        3,
        "approach",
        "Explain the key insight or what goes wrong in plain words, including the target "
        "complexity. No code, no pseudocode, no full list of steps.",
    ),
    4: HelpLevel(
        4,
        "pseudocode",
        "You may give a step-by-step outline or language-neutral pseudocode, and describe "
        "the fix in words. No runnable code.",
    ),
    5: HelpLevel(
        5,
        "solution",
        "You may give the full solution or the fixed code with a short explanation. "
        "Prefer the smallest change to the user's code.",
    ),
}


def help_level(level: int) -> HelpLevel:
    """The HelpLevel for 0-5. Anything else is a bug in the caller."""
    if level not in HELP_LEVELS:
        raise ValueError(f"help level must be 0 to 5, got {level}")
    return HELP_LEVELS[level]
