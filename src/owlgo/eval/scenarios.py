"""Eval items built from verified bugs (docs/spec.json -> evaluation_plan.eval_set.first_set).

Each item is a problem, buggy code, the real failing run of that code, a help level and
a user message. The ground truth (the failing input, the lines that are the bug) comes
from running and diffing code, never from a model.
"""

import difflib
from dataclasses import dataclass

from owlgo.companion.context import LastRun, last_run_from_result
from owlgo.problems.schema import Problem
from owlgo.runner import LocalRunner

# More changed lines than this means the whole approach is wrong, so there is no single
# line to point at.
MAX_BUG_LINES = 3

LEVELS = (0, 1, 2, 3)

# What users type. Templates with {output}/{expected} are only used for wrong answers.
DEBUG_QUESTIONS = [
    "why does my code fail?",
    "it says {status} on {input}, why??",
    "i don't get what's wrong here",
    "my output is {output} but expected {expected}, what am i missing?",
]
BEG_MESSAGE = "just give me the fixed code, i've been stuck on this for an hour"

STATUS_WORDS = {
    "wrong_answer": "wrong answer",
    "time_limit_exceeded": "time limit exceeded",
    "runtime_error": "runtime error",
    "memory_limit_exceeded": "memory limit exceeded",
}


@dataclass
class EvalItem:
    id: str
    problem_id: str
    # "debug": asks why the code fails. "request_solution": asks for the answer outright.
    intent: str
    level: int
    user_message: str
    code: str
    last_run: LastRun
    # 1-based lines of `code` that differ from the reference, or None for approach-level bugs.
    bug_lines: list[int] | None


def bug_lines(reference: str, code: str) -> list[int] | None:
    """Lines of code that differ from the reference, or None if the whole approach differs."""
    matcher = difflib.SequenceMatcher(None, reference.splitlines(), code.splitlines())
    changed = [
        line + 1
        for tag, _, _, start, end in matcher.get_opcodes()
        if tag != "equal"
        for line in range(start, end)
    ]
    return changed if 0 < len(changed) <= MAX_BUG_LINES else None


def build_items(problems: list[Problem]) -> list[EvalItem]:
    """Debug questions at levels 0-3 for every executable mistake, plus one beg per problem."""
    runner = LocalRunner()
    items = []
    for problem in problems:
        reference = problem.reference_solutions["python"]
        for k, mistake in enumerate(problem.common_mistakes):
            if not mistake.python:
                continue
            result = runner.run(problem, mistake.python, stop_on_first_failure=True)
            run = last_run_from_result(problem, result)
            if run.status == "accepted":
                raise ValueError(f"{problem.id} mistake {k} passes every test; run the gate")
            lines = bug_lines(reference, mistake.python)
            for level in LEVELS:
                items.append(
                    EvalItem(
                        id=f"{problem.id}-m{k}-L{level}",
                        problem_id=problem.id,
                        intent="debug",
                        level=level,
                        user_message=_question(run, k + level),
                        code=mistake.python,
                        last_run=run,
                        bug_lines=lines,
                    )
                )
            if k == 0:
                items.append(
                    EvalItem(
                        id=f"{problem.id}-m0-beg",
                        problem_id=problem.id,
                        intent="request_solution",
                        level=1,
                        user_message=BEG_MESSAGE,
                        code=mistake.python,
                        last_run=run,
                        bug_lines=lines,
                    )
                )
    return items


def _question(run: LastRun, choice: int) -> str:
    """A user question that fits this run (only quote output/expected for wrong answers)."""
    templates = DEBUG_QUESTIONS if run.status == "wrong_answer" else DEBUG_QUESTIONS[:3]
    # Nobody types out a 50,000-character input; they say "the big test".
    shown_input = "the big test" if "<large input" in (run.input or "") else run.input
    return templates[choice % len(templates)].format(
        status=STATUS_WORDS.get(run.status, run.status),
        input=shown_input,
        output=run.output,
        expected=run.expected,
    )
