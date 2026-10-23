"""Prompt variants, and the spoiler guard's rules at every help level."""

import pytest

from owlgo.companion.context import Context, render
from owlgo.companion.guard import SAFE_REPLIES, check_reply, guarded_chat
from owlgo.companion.prompt import BEHAVIOR_RULES, build_messages, system_prompt
from owlgo.llm_client import Reply
from owlgo.problems.loader import DEFAULT_PROBLEMS_DIR, load_problem

CONTEXT = Context("Title", "easy", "Statement.", "python", "x = 1", help_level=1)
WARMER = load_problem(DEFAULT_PROBLEMS_DIR / "original" / "days-until-warmer.json")


# --- Prompts ----------------------------------------------------------------------------------


def test_variants():
    assert system_prompt(CONTEXT, "minimal") == render(CONTEXT)
    assert system_prompt(CONTEXT, "prompted").endswith(BEHAVIOR_RULES)
    with pytest.raises(ValueError):
        system_prompt(CONTEXT, "unknown")


def test_messages_keep_only_recent_history():
    history = [{"role": "user", "content": str(i)} for i in range(10)]
    messages = build_messages(CONTEXT, "why?", history)
    assert messages[0]["role"] == "system" and messages[-1]["content"] == "why?"
    assert [m["content"] for m in messages[1:-1]] == ["4", "5", "6", "7", "8", "9"]


# --- Guard checks -----------------------------------------------------------------------------

CODE_REPLY = "Try this:\n```python\nreturn best\n```"
CODE_LINES = "Change it to:\nfor i in range(n):\n    best = max(best, i)\nreturn best"
STEPS = "1. Make a stack.\n2. Push each day.\n3. Pop colder days."
INLINE_STEPS = "First 1) keep a list, 2) walk the days, 3) settle the colder ones."


@pytest.mark.parametrize(
    "reply, level, expected",
    [
        (CODE_REPLY, 4, ["code_block"]),
        (CODE_REPLY, 5, []),
        (CODE_LINES, 3, ["code_block"]),
        (STEPS, 3, ["ordered_steps"]),
        (STEPS, 4, []),
        (INLINE_STEPS, 2, ["ordered_steps"]),
        ("A stack could help here.", 1, ["approach_name"]),
        ("A stack could help here.", 2, []),
        ("Which day answers day 0 first?", 0, []),
        ("A hash map gives O(1) lookups, and O(n) total.", 3, []),
        ("", 3, ["empty_reply"]),
    ],
)
def test_check_reply(reply, level, expected):
    found = [v.check for v in check_reply(reply, level, WARMER)]
    assert found == expected


def test_naming_a_technique_the_user_already_uses_is_fine():
    code = "stack = []\nfor t in temps:\n    pass\n"
    assert check_reply("Your stack keeps every day.", 1, WARMER, code=code) == []
    assert (
        check_reply("What does a monotonic stack mean?", 1, WARMER, user_text="monotonic stack?")
        == []
    )


def test_one_line_that_looks_like_code_is_fine():
    assert check_reply("At that point left = 2, right?", 1) == []


# --- Guarded chat -----------------------------------------------------------------------------


class ScriptedClient:
    """Returns the given replies in order, like a model would."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return Reply(self.texts.pop(0), "", "stop", 0, 0, 0.0)


def test_good_reply_passes_on_the_first_try():
    client = ScriptedClient("Which day settles day 0?")
    result = guarded_chat(client, [{"role": "user", "content": "help"}], level=1, problem=WARMER)
    assert result.text == "Which day settles day 0?" and len(client.calls) == 1


def test_bad_reply_is_regenerated_with_a_warning():
    client = ScriptedClient(CODE_REPLY, "Look at line 4: which days are still waiting?")
    result = guarded_chat(client, [{"role": "user", "content": "help"}], level=1, problem=WARMER)
    assert result.text.startswith("Look at line 4") and not result.used_fallback
    warning = client.calls[1][-1]["content"]
    assert "help level 1" in warning and "code_block" in warning


def test_two_bad_replies_fall_back_to_a_safe_reply():
    client = ScriptedClient(CODE_REPLY, STEPS)
    result = guarded_chat(client, [{"role": "user", "content": "help"}], level=0, problem=WARMER)
    assert result.used_fallback and result.text == SAFE_REPLIES[0]
    assert [v[0].check for v in result.violations] == ["code_block", "ordered_steps"]
