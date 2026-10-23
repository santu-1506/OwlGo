"""The context block must show the model exactly what a user would see, and nothing else."""

import pytest

from owlgo.companion.context import (
    MAX_CODE_LINES,
    Context,
    LastRun,
    context_for,
    last_run_from_result,
    number_lines,
    render,
    render_input,
)
from owlgo.companion.dial import help_level
from owlgo.problems.loader import DEFAULT_PROBLEMS_DIR, load_problem
from owlgo.runner import LocalRunner

SUBSTRING = load_problem(DEFAULT_PROBLEMS_DIR / "original" / "longest-substring-no-repeat.json")
# Common mistake 0: the left pointer can move backwards (fails on "abba").
BUGGY = SUBSTRING.common_mistakes[0].python


def test_code_gets_right_aligned_line_numbers():
    assert number_lines("a = 1\nb = 2\n") == " 1| a = 1\n 2| b = 2"
    assert number_lines("") == "(no code yet)"
    long = number_lines("\n".join(f"x{i} = {i}" for i in range(MAX_CODE_LINES + 5)))
    assert long.endswith("(5 more lines not shown)")


def test_real_failing_run_becomes_the_last_run():
    result = LocalRunner().run(SUBSTRING, BUGGY, stop_on_first_failure=True)
    run = last_run_from_result(SUBSTRING, result)
    assert (run.status, run.input, run.expected, run.output) == (
        "wrong_answer",
        "s = 'abba'",
        "2",
        "3",
    )


def test_runtime_errors_show_the_error_and_line():
    result = LocalRunner().run(SUBSTRING, "def solve(s):\n    return len(s) // 0\n")
    run = last_run_from_result(SUBSTRING, result)
    assert run.status == "runtime_error" and run.error_line == 2
    assert "ZeroDivisionError" in run.error and run.expected is None


def test_accepted_run():
    result = LocalRunner().run(SUBSTRING, SUBSTRING.reference_solutions["python"])
    assert last_run_from_result(SUBSTRING, result).status == "accepted"


def test_large_generated_inputs_are_described_not_dumped():
    stress = next(test for test in SUBSTRING.tests if test.stress)
    assert render_input(SUBSTRING, stress) == "s = <large input: cycle_printable_ascii(n=50000)>"


def test_rendered_block_has_every_section():
    run = LastRun(status="wrong_answer", input="s = 'abba'", expected="2", output="3")
    text = render(context_for(SUBSTRING, BUGGY, level=1, last_run=run))
    assert "## Help level\n1 (nudge): " + help_level(1).rule in text
    assert "Longest Substring Without Repeating Characters (medium)" in text
    assert " 6|         if ch in last:" in text
    assert text.endswith(
        "kind: run\nstatus: wrong_answer\ninput: s = 'abba'\nexpected: 2\noutput: 3"
    )


def test_no_run_yet_and_solved_marker():
    context = Context("T", "easy", "S", "python", "", help_level=0, solved=True)
    text = render(context)
    assert "T (easy) - solved" in text and text.endswith("(not run yet)")


def test_help_level_must_be_0_to_5():
    with pytest.raises(ValueError):
        help_level(6)
