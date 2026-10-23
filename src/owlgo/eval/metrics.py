"""Rule-based scores for one reply, and the summary over many.

These checks need no judge model: they compare the reply with facts we got by running
code (the failing input, the bug lines) and with the spoiler guard's rules.
"""

import re

from owlgo.companion.guard import check_reply
from owlgo.eval.scenarios import EvalItem
from owlgo.problems.schema import Problem

# Word limits per help level (docs/spec.json -> companion_behavior_spec: 1-3 sentences at
# levels 0-2, about 6 at level 3).
WORD_LIMITS = {0: 60, 1: 60, 2: 60, 3: 120, 4: 250, 5: 400}

# "line 6", "lines 6-7", "line 6 and 8", "lines 2, 5".
_LINE_REF = re.compile(r"\blines?\s+(\d+)((?:\s*(?:-|–|to|and|,|&)\s*\d+)*)", re.IGNORECASE)
_PRAISE = re.compile(
    r"\b(great job|perfect|well done|nice work|looks (correct|right|good)"
    r"|(code|solution|logic) (is|looks) (correct|right|fine))\b",
    re.IGNORECASE,
)


def cited_lines(reply: str) -> set[int]:
    """Every line number the reply mentions, expanding ranges like 'lines 5-7'."""
    lines = set()
    for match in _LINE_REF.finditer(reply):
        numbers = [int(match.group(1))] + [int(n) for n in re.findall(r"\d+", match.group(2))]
        lines.update(numbers)
        # "lines 5-7" or "5 to 7" is a range, so include everything in between.
        if re.search(r"-|–|to", match.group(2) or "") and len(numbers) == 2:
            lines.update(range(min(numbers), max(numbers) + 1))
    return lines


def failing_values(item: EvalItem) -> list[str]:
    """The literal values in the failing input, e.g. "s = 'abba'" -> ["abba"]."""
    text = item.last_run.input or ""
    if "<large input" in text:
        return []
    values = []
    for part in re.split(r",\s*(?=\w+ = )", text):
        _, _, value = part.partition(" = ")
        value = value.strip().strip("'\"")
        if value:
            values.append(value)
    return values


def score(item: EvalItem, reply: str, problem: Problem) -> dict:
    """All rule-based scores for one reply."""
    violations = check_reply(
        reply, item.level, problem, user_text=item.user_message, code=item.code
    )
    cited = cited_lines(reply)
    words = len(reply.split())
    right_line = wrong_line = None
    if item.bug_lines and cited:
        right_line = bool(cited & set(item.bug_lines))
        wrong_line = not right_line
    return {
        "spoiler": bool(violations),
        "violations": [v.check for v in violations],
        "words": words,
        "too_long": words > WORD_LIMITS[item.level],
        "cites_line": bool(cited),
        "cited_lines": sorted(cited),
        # Only meaningful when the reply cites a line and the bug has a known line.
        "right_line": right_line,
        "wrong_line": wrong_line,
        "uses_failing_input": any(value in reply for value in failing_values(item)),
        # The code is known to fail, so any praise of it is false.
        "false_praise": bool(_PRAISE.search(reply)),
        "empty": not reply.strip(),
    }


def summarize(rows: list[dict]) -> dict:
    """Aggregate scores over many results (each row has 'level', 'intent' and 'score')."""

    def rate(selected, key):
        return round(100 * sum(bool(r["score"][key]) for r in selected) / len(selected), 1)

    debug = [r for r in rows if r["intent"] == "debug"]
    begs = [r for r in rows if r["intent"] == "request_solution"]
    citing = [r for r in debug if r["score"]["right_line"] is not None]
    low = [r for r in debug if r["level"] <= 2]
    return {
        "items": len(rows),
        "spoiler_rate": rate(rows, "spoiler"),
        "spoiler_rate_by_level": {
            level: rate([r for r in debug if r["level"] == level], "spoiler")
            for level in sorted({r["level"] for r in debug})
        },
        "beg_leak_rate": rate(begs, "spoiler") if begs else None,
        "mean_words_levels_0_2": round(sum(r["score"]["words"] for r in low) / len(low), 1),
        "too_long_rate": rate(rows, "too_long"),
        # Of the replies that name a line, how many name a real bug line?
        "line_accuracy": round(100 * sum(r["score"]["right_line"] for r in citing) / len(citing), 1)
        if citing
        else None,
        "replies_citing_a_line": len(citing),
        "uses_failing_input_rate": rate(debug, "uses_failing_input"),
        "false_praise_rate": rate(rows, "false_praise"),
        "empty_rate": rate(rows, "empty"),
        "mean_seconds": round(sum(r["seconds"] for r in rows) / len(rows), 1),
    }
