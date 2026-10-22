"""The EvalPlus importer must read tests exactly and skip what it can't reproduce."""

import pytest

from owlgo.problems.import_evalplus import (
    Skip,
    drop_heavy_tests,
    function_info,
    humaneval_problem,
    mbpp_problem,
    parse_test_source,
)

# Shortened copies of real EvalPlus test blocks.
STANDARD_ASSERTION = """
import numpy as np
from math import inf

def assertion(out, exp, atol):
    if atol == 0 and is_floats(exp):
        atol = 1e-6
    if out != exp and atol != 0:
        assert np.allclose(out, exp, rtol=1e-07, atol=atol)
    else:
        assert out == exp, f"out: {out}, exp: {exp}"
"""

SET_ASSERTION = STANDARD_ASSERTION.replace(
    "        atol = 1e-6\n", "        atol = 1e-6\n    out = set(out)\n    exp = set(exp)\n"
)


def mbpp_test(assertion, inputs, results, name="add", atol=0):
    return (
        f"{assertion}\ninputs = {inputs}\nresults = {results}\n"
        f"for i, (inp, exp) in enumerate(zip(inputs, results)):\n"
        f"    assertion({name}(*inp), exp, {atol})\n"
    )


def test_reads_inputs_results_and_atol():
    parsed = parse_test_source(
        mbpp_test(STANDARD_ASSERTION, "[[1, 2], [3, inf]]", "[3, inf]", atol=0.0001)
    )
    assert parsed["inputs"] == [[1, 2], [3, float("inf")]]
    assert parsed["results"] == [3, float("inf")]
    assert (parsed["mode"], parsed["atol"]) == ("exact", 0.0001)


def test_detects_set_comparison():
    assert parse_test_source(mbpp_test(SET_ASSERTION, "[[1]]", "[(1,)]"))["mode"] == "set"


def test_skips_expected_values_computed_by_a_helper():
    source = mbpp_test(STANDARD_ASSERTION, "[[1, 2]]", "[3]").replace(
        "assertion(add(*inp), exp, 0)", "assertion(add(*inp), ref_func(*inp), 0)"
    )
    with pytest.raises(Skip, match="computed by a helper"):
        parse_test_source(source)


def test_skips_custom_comparisons():
    custom = "def assertion(out, exp, atol):\n    exact_match = exp == (out is not None)\n"
    with pytest.raises(Skip, match="custom comparison"):
        parse_test_source(mbpp_test(custom, "[[1]]", "[True]"))


def test_never_executes_test_data():
    # A function call in the data must be refused, not run.
    with pytest.raises(Skip, match="not a plain literal"):
        parse_test_source(mbpp_test(STANDARD_ASSERTION, "[[__import__('os')]]", "[1]"))


def test_function_info_reads_params_and_signature():
    info = function_info("def f(a: int, b=2) -> int:\n    '''Add.'''\n    return a + b\n", "f")
    assert info == {
        "params": ["a", "b"],
        "signature": "def f(a: int, b=2) -> int:",
        "docstring": "Add.",
    }
    with pytest.raises(Skip, match=r"\*args"):
        function_info("def f(*xs):\n    return 0\n", "f")


def test_mbpp_row_becomes_a_problem():
    row = {
        "task_id": 7,
        "prompt": "Write a function to add two numbers.",
        "code": "def add_Nums(a, b):\n    return a + b\n",
        "test": mbpp_test(
            STANDARD_ASSERTION, "[[1, 2], [3, 4], [0, 0], [1, 2]]", "[3, 7, 0, 3]", name="add_Nums"
        ),
    }
    problem = mbpp_problem(row)
    assert problem.id == "mbpp-7-add-nums" and problem.params == ["a", "b"]
    # The duplicate fourth test is dropped.
    assert [t.output for t in problem.tests] == [3, 7, 0]


def test_humaneval_row_uses_the_docstring_as_statement():
    test = mbpp_test(STANDARD_ASSERTION, "[[1], [2], [3]]", "[2, 3, 4]", name="candidate")
    row = {
        "task_id": "HumanEval/9",
        "prompt": 'def inc(x: int) -> int:\n    """Return x + 1."""\n',
        "canonical_solution": "    return x + 1\n",
        "entry_point": "inc",
        "test": "def check(candidate):\n" + "\n".join("    " + line for line in test.splitlines()),
    }
    problem = humaneval_problem(row)
    assert problem.id == "humaneval-9-inc" and problem.statement == "Return x + 1."


def test_slow_tests_are_dropped_but_failing_ones_are_kept():
    # The reference is slow on a == 9 and wrong on a == 5 (expected 99 is false).
    code = "import time\ndef f(a):\n    if a == 9:\n        time.sleep(0.2)\n    return a\n"
    row = {
        "task_id": 3,
        "prompt": "p",
        "code": code,
        "test": mbpp_test(STANDARD_ASSERTION, "[[1], [2], [9], [5]]", "[1, 2, 9, 99]", name="f"),
    }
    trimmed, removed = drop_heavy_tests(mbpp_problem(row))
    assert removed == 1
    # The slow test is gone; the failing one stays so the gate can still reject the problem.
    assert [t.output for t in trimmed.tests] == [1, 2, 99]


def test_too_few_tests_are_skipped():
    row = {
        "task_id": 1,
        "prompt": "p",
        "code": "def f(a):\n    return a\n",
        "test": mbpp_test(STANDARD_ASSERTION, "[[1]]", "[1]", name="f"),
    }
    with pytest.raises(Skip, match="usable tests"):
        mbpp_problem(row)
