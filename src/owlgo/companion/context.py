"""The context block: everything the companion sees before each reply.

This text is a contract shared by training data, evaluation and the Chrome
extension (docs/spec.json -> context_block). Change it only here, and bump
CONTEXT_VERSION when you do, because a fine-tuned model learns this exact layout.
"""

from dataclasses import dataclass

from owlgo.companion.dial import help_level
from owlgo.problems.schema import Problem, ProblemTest
from owlgo.runner.results import RunResult
from owlgo.values import UnsupportedValue, decode

CONTEXT_VERSION = 1

# Limits that keep the whole block well inside the model's context window.
MAX_STATEMENT_CHARS = 1500
MAX_CODE_LINES = 200
MAX_VALUE_CHARS = 300

TEMPLATE = (
    "You are Owlgo, a friendly DSA practice companion. "
    "Never give more help than the help level allows.\n\n"
    "## Help level\n{level} ({level_name}): {level_rule}\n\n"
    "## Problem\n{title} ({difficulty}){solved}\n{statement}\n\n"
    "## Language\n{language}\n\n"
    "## User's code\n{code}\n\n"
    "## Last run\n{last_run}"
)


@dataclass
class LastRun:
    """The latest Run or Submit result, as the user saw it."""

    status: str
    kind: str = "run"
    # Already rendered for display, e.g. "s = 'abba'".
    input: str | None = None
    expected: str | None = None
    output: str | None = None
    error: str | None = None
    error_line: int | None = None


@dataclass
class Context:
    """Inputs to the context block."""

    title: str
    difficulty: str
    statement: str
    language: str
    code: str
    help_level: int
    last_run: LastRun | None = None
    solved: bool = False


def render(context: Context) -> str:
    """The full context block text."""
    level = help_level(context.help_level)
    statement = context.statement.strip()
    if len(statement) > MAX_STATEMENT_CHARS:
        statement = statement[:MAX_STATEMENT_CHARS] + " ... (statement cut)"
    return TEMPLATE.format(
        level=level.level,
        level_name=level.name,
        level_rule=level.rule,
        title=context.title,
        difficulty=context.difficulty,
        solved=" - solved" if context.solved else "",
        statement=statement,
        language=context.language,
        code=number_lines(context.code),
        last_run=render_last_run(context.last_run),
    )


def number_lines(code: str) -> str:
    """Code with right-aligned line numbers ('  6| if ch in last:'), cut after MAX_CODE_LINES."""
    lines = code.rstrip().splitlines()
    if not lines:
        return "(no code yet)"
    shown = lines[:MAX_CODE_LINES]
    width = max(2, len(str(len(shown))))
    numbered = [f"{number:>{width}}| {line}" for number, line in enumerate(shown, start=1)]
    if len(lines) > MAX_CODE_LINES:
        numbered.append(f"... ({len(lines) - MAX_CODE_LINES} more lines not shown)")
    return "\n".join(numbered)


def render_last_run(run: LastRun | None) -> str:
    """The 'Last run' section, listing only the fields that apply."""
    if run is None:
        return "(not run yet)"
    lines = [f"kind: {run.kind}", f"status: {run.status}"]
    for label, value in [
        ("input", run.input),
        ("expected", run.expected),
        ("output", run.output),
        ("error", run.error),
        ("error line", run.error_line),
    ]:
        if value is not None:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def context_for(problem: Problem, code: str, level: int, last_run: LastRun | None) -> Context:
    """A Context for a problem from the bank."""
    return Context(
        title=problem.title,
        difficulty=problem.difficulty,
        statement=problem.statement,
        language="python",
        code=code,
        help_level=level,
        last_run=last_run,
    )


def last_run_from_result(problem: Problem, result: RunResult, kind: str = "run") -> LastRun:
    """Describe a run the way a judge shows it: the first failing test and what went wrong."""
    failure = result.first_failure
    if failure is None:
        return LastRun(status="accepted", kind=kind)
    run = LastRun(status=failure.status, kind=kind)
    # A compile error has no particular input: the code never ran.
    if failure.status != "compile_error":
        run.input = render_input(problem, problem.tests[failure.index])
    if failure.status == "wrong_answer":
        run.expected = show_value(failure.expected)
        run.output = show_value(failure.output)
    run.error = failure.error
    run.error_line = failure.error_line
    return run


def render_input(problem: Problem, test: ProblemTest) -> str:
    """A test's input as the user would see it, e.g. "nums = [1, 2], k = 3"."""
    if problem.io_mode == "stdio":
        return _cut(repr(test.stdin))
    parts = []
    for name in problem.params:
        if name in test.input:
            parts.append(f"{name} = {show_value(test.input[name])}")
        elif name in test.generated_inputs:
            spec = test.generated_inputs[name]
            args = ", ".join(f"{key}={value!r}" for key, value in spec.args.items())
            parts.append(f"{name} = <large input: {spec.fn}({args})>")
    return ", ".join(parts)


def show_value(encoded) -> str:
    """An encoded value as Python would print it, cut to MAX_VALUE_CHARS."""
    if isinstance(encoded, dict) and set(encoded) == {"$repr"}:
        return _cut(encoded["$repr"])
    try:
        return _cut(repr(decode(encoded)))
    except UnsupportedValue:
        return _cut(str(encoded))


def _cut(text: str) -> str:
    return text if len(text) <= MAX_VALUE_CHARS else text[:MAX_VALUE_CHARS] + "..."
