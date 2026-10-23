"""The spoiler guard: rule-based checks that a reply never gives more help than allowed.

Checks (docs/spec.json -> spoiler_guard), by help level:
- empty_reply (all levels): the model returned nothing visible.
- code_block (below 5): fenced code, or more than 2 lines that look like code.
- ordered_steps (below 4): 3 or more numbered steps.
- approach_name (below 2): naming the problem's technique, unless the user already used
  or mentioned it.

guarded_chat() runs a reply through the checks, regenerates once with a warning if it
fails, and falls back to a safe template reply if the second try fails too.
"""

import re
from dataclasses import dataclass, field

from owlgo.llm_client import LLMClient, Reply
from owlgo.problems.schema import Problem

# Lines that read like code rather than prose.
_CODE_LINE = re.compile(
    r"^\s*(def |class |for .+ in .+:|while .+:|if .+:|elif .+:|else:|return\b|import \w"
    r"|from \S+ import|[A-Za-z_][\w.\[\]]*\s*(=|\+=|-=)\s*\S)"
)
# A numbered step at the start of a line: "1.", "2)", "Step 3".
_STEP_LINE = re.compile(r"^\s*(\(?[1-9][0-9]?[.)]\s|step\s+[1-9])", re.IGNORECASE)
# A numbered step inside a sentence: "... 1) do this 2) then that". "O(1) " doesn't count.
_INLINE_STEP = re.compile(r"(?<![(\w])[1-9][.)]\s")

# Words that name each pattern's technique (approach_name check).
PATTERN_PHRASES = {
    "arrays_and_hashing": ["hash map", "hashmap", "hash set", "hashset", "hash table"],
    "two_pointers": ["two pointers", "two-pointer", "two pointer"],
    "sliding_window": ["sliding window"],
    "stack": ["stack", "monotonic"],
    "binary_search": ["binary search", "bisect"],
    "linked_list": ["fast and slow pointer", "dummy node"],
    "trees": ["recursion", "dfs", "bfs"],
    "tries": ["trie", "prefix tree"],
    "heap": ["heap", "priority queue"],
    "backtracking": ["backtrack"],
    "graphs_bfs_dfs": ["bfs", "dfs", "breadth-first", "depth-first", "union find"],
    "dynamic_programming_1d": ["dynamic programming", "dp array", "memoiz"],
    "dynamic_programming_2d": ["dynamic programming", "dp table", "memoiz"],
    "greedy": ["greedy"],
    "intervals": ["sweep line"],
    "bit_manipulation": ["bitmask", "xor"],
}

# Sent when both tries break the rules: safe, generic and still useful.
SAFE_REPLIES = {
    0: "Walk me through what your code does on the failing input, one line at a time. "
    "What did you expect each variable to hold?",
    1: "Trace the failing input by hand. At which step does a variable first get a value "
    "you didn't expect?",
    2: "Compare what your code does with what the problem needs on the failing input. "
    "Which part of the code is the first place they disagree?",
    3: "Let's look at the idea before the code. On the failing input, what should happen "
    "at each step, and where does your code do something different?",
    4: "Let's outline it in words first. What are the main steps your solution needs, and "
    "which one does your code handle differently?",
}

RETRY_NOTE = (
    "(Owlgo check) Your last reply gave more help than help level {level} allows "
    "({checks}). Reply again, staying at level {level}."
)


@dataclass
class Violation:
    check: str
    detail: str


def check_reply(
    reply: str, level: int, problem: Problem | None = None, user_text: str = "", code: str = ""
) -> list[Violation]:
    """Every rule the reply breaks at this help level. Empty means it's fine."""
    violations = []
    if not reply.strip():
        return [Violation("empty_reply", "the reply has no visible text")]
    if level < 5:
        code_lines = [line for line in reply.splitlines() if _CODE_LINE.match(line)]
        if "```" in reply:
            violations.append(Violation("code_block", "fenced code block"))
        elif len(code_lines) > 2:
            violations.append(Violation("code_block", f"{len(code_lines)} lines of code"))
    if level < 4:
        steps = sum(bool(_STEP_LINE.match(line)) for line in reply.splitlines())
        steps = max(steps, len(_INLINE_STEP.findall(reply)))
        if steps >= 3:
            violations.append(Violation("ordered_steps", f"{steps} numbered steps"))
    if level < 2 and problem is not None:
        named = _named_techniques(reply, problem, already_used=f"{user_text}\n{code}")
        if named:
            violations.append(Violation("approach_name", "names " + ", ".join(named)))
    return violations


def _named_techniques(reply: str, problem: Problem, already_used: str) -> list[str]:
    """Technique names in the reply that the user hasn't used or mentioned themselves."""
    phrases = [
        phrase for pattern in problem.patterns for phrase in PATTERN_PHRASES.get(pattern, [])
    ]
    if problem.optimal:
        phrases.append(problem.optimal.approach_name)
    found = []
    for phrase in dict.fromkeys(phrases):
        pattern = re.compile(rf"\b{re.escape(phrase)}", re.IGNORECASE)
        if pattern.search(reply) and not pattern.search(already_used):
            found.append(phrase)
    return found


@dataclass
class GuardedReply:
    """The reply to show, and what happened on the way there."""

    text: str
    # True when both tries broke the rules and a safe template was sent instead.
    used_fallback: bool
    # The raw model replies, one per try, and the rules each one broke.
    replies: list[Reply] = field(default_factory=list)
    violations: list[list[Violation]] = field(default_factory=list)


def guarded_chat(
    client: LLMClient,
    messages: list[dict],
    level: int,
    problem: Problem | None = None,
    user_text: str = "",
    code: str = "",
) -> GuardedReply:
    """Get a reply that passes the guard: first try, one regeneration, then a safe fallback."""
    result = GuardedReply(text="", used_fallback=False)
    attempt_messages = list(messages)
    for _ in range(2):
        reply = client.chat(attempt_messages)
        violations = check_reply(reply.text, level, problem, user_text, code)
        result.replies.append(reply)
        result.violations.append(violations)
        if not violations:
            result.text = reply.text
            return result
        # Show the model its own reply and what was wrong with it, then ask again.
        checks = ", ".join(v.check for v in violations)
        attempt_messages = messages + [
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": RETRY_NOTE.format(level=level, checks=checks)},
        ]
    result.text = SAFE_REPLIES.get(level, SAFE_REPLIES[4])
    result.used_fallback = True
    return result
