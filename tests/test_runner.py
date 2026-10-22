"""LocalRunner must report every outcome correctly, because training data is built on it."""

import pytest

from owlgo.problems.schema import Problem
from owlgo.runner import LocalRunner


def function_problem(tests, params=("a", "b"), **extra):
    """A small function problem with the given tests."""
    return Problem.model_validate(
        {
            "id": "runner-test",
            "title": "Runner Test",
            "source": "original",
            "license": "MIT",
            "difficulty": "easy",
            "statement": "Used by the runner tests.",
            "entry_point": "solve",
            "params": list(params),
            "tests": tests,
            "reference_solutions": {"python": "def solve(a, b):\n    return a + b\n"},
            **extra,
        }
    )


ADD_TESTS = [{"input": {"a": 1, "b": 2}, "output": 3}, {"input": {"a": 0, "b": 0}, "output": 0}]


@pytest.fixture
def runner():
    # Short limits keep the suite fast.
    return LocalRunner(per_test_seconds=0.5, backstop_padding_seconds=2.0)


def test_correct_code_is_accepted(runner):
    result = runner.run(function_problem(ADD_TESTS), "def solve(a, b):\n    return a + b\n")
    assert result.verdict == "accepted" and result.passed_count == 2


def test_wrong_answer_reports_output_and_expected(runner):
    result = runner.run(function_problem(ADD_TESTS), "def solve(a, b):\n    return a - b\n")
    failure = result.first_failure
    assert result.verdict == "wrong_answer"
    assert (failure.index, failure.output, failure.expected) == (0, -1, 3)


def test_runtime_error_reports_the_line(runner):
    code = "def solve(a, b):\n    x = a + b\n    return x // 0\n"
    failure = runner.run(function_problem(ADD_TESTS), code).first_failure
    assert failure.status == "runtime_error"
    assert failure.error_line == 3 and "ZeroDivisionError" in failure.error


def test_syntax_error_fails_every_test(runner):
    result = runner.run(function_problem(ADD_TESTS), "def solve(a, b)\n    return a\n")
    assert [t.status for t in result.tests] == ["compile_error", "compile_error"]
    assert result.tests[0].error_line == 1


def test_missing_function_is_a_compile_error(runner):
    result = runner.run(function_problem(ADD_TESTS), "def other(a, b):\n    return 0\n")
    assert result.verdict == "compile_error" and "'solve' is not defined" in result.tests[0].error


def test_slow_test_times_out_and_later_tests_still_run(runner):
    # Loops forever only when a == 1, so test 0 times out and test 1 passes.
    code = "def solve(a, b):\n    while a == 1:\n        pass\n    return a + b\n"
    result = runner.run(function_problem(ADD_TESTS), code)
    assert [t.status for t in result.tests] == ["time_limit_exceeded", "passed"]


def test_except_exception_cannot_swallow_the_timeout(runner):
    code = (
        "def solve(a, b):\n    try:\n        while True:\n            pass\n"
        "    except Exception:\n        return a + b\n"
    )
    assert runner.run(function_problem(ADD_TESTS[:1]), code).verdict == "time_limit_exceeded"


def test_backstop_kills_code_that_ignores_the_alarm(runner):
    # Ignoring SIGALRM defeats the per-test timer; the process-level backstop must still win.
    code = (
        "import signal\n"
        "def solve(a, b):\n    signal.signal(signal.SIGALRM, signal.SIG_IGN)\n"
        "    while True:\n        pass\n"
    )
    result = runner.run(function_problem(ADD_TESTS), code)
    assert [t.status for t in result.tests] == ["time_limit_exceeded", "not_run"]


def test_stop_on_first_failure_skips_the_rest(runner):
    result = runner.run(
        function_problem(ADD_TESTS), "def solve(a, b):\n    return 99\n", stop_on_first_failure=True
    )
    assert [t.status for t in result.tests] == ["wrong_answer", "not_run"]


def test_prints_are_captured_without_breaking_results(runner):
    code = "def solve(a, b):\n    print('debug', a)\n    return a + b\n"
    result = runner.run(function_problem(ADD_TESTS[:1]), code)
    assert result.verdict == "accepted" and result.tests[0].stdout == "debug 1\n"


def test_tuple_and_list_answers_are_different(runner):
    problem = function_problem([{"input": {"a": 1, "b": 2}, "output": {"$tuple": [1, 2]}}])
    result = runner.run(problem, "def solve(a, b):\n    return [a, b]\n")
    assert result.verdict == "wrong_answer"


def test_set_comparison_ignores_order(runner):
    problem = function_problem(
        [{"input": {"a": 1, "b": 2}, "output": {"$tuple": [1, 2]}}], comparison={"mode": "set"}
    )
    assert runner.run(problem, "def solve(a, b):\n    return (b, a)\n").verdict == "accepted"


def test_float_outputs_get_a_small_tolerance(runner):
    problem = function_problem([{"input": {"a": 0.1, "b": 0.2}, "output": 0.3}])
    assert runner.run(problem, "def solve(a, b):\n    return a + b\n").verdict == "accepted"


def test_generated_inputs_and_outputs(runner):
    problem = function_problem(
        [
            {
                "generated_inputs": {"nums": {"fn": "arange", "args": {"start": 0, "stop": 1000}}},
                "generated_output": {
                    "fn": "arange",
                    "args": {"start": 999, "stop": -1, "step": -1},
                },
            }
        ],
        params=("nums",),
    )
    code = "def solve(nums):\n    return nums[::-1]\n"
    assert runner.run(problem, code).verdict == "accepted"


def test_stdio_problems(runner):
    problem = Problem.model_validate(
        {
            "id": "stdio-sum",
            "title": "Stdio Sum",
            "source": "original",
            "license": "MIT",
            "difficulty": "easy",
            "statement": "Read two ints and print their sum.",
            "io_mode": "stdio",
            "tests": [{"stdin": "1 2\n", "output": "3\n"}, {"stdin": "5 5\n", "output": "10"}],
            "reference_solutions": {"python": "a, b = map(int, input().split())\nprint(a + b)\n"},
        }
    )
    right = "a, b = map(int, input().split())\nprint(a + b)\n"
    wrong = "a, b = map(int, input().split())\nprint(a * b)\n"
    assert runner.run(problem, right).verdict == "accepted"
    assert runner.run(problem, wrong).first_failure.output == "2\n"
