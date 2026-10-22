"""The verification gate must reject every kind of unproven claim."""

from owlgo.problems.schema import Problem
from owlgo.problems.verify import verify_problem
from owlgo.runner import LocalRunner

ADD = "def solve(a, b):\n    return a + b\n"


def make_problem(**overrides):
    """A small problem that passes the gate; tests override fields to break it."""
    problem = {
        "id": "add-two",
        "title": "Add Two",
        "source": "original",
        "license": "MIT",
        "difficulty": "easy",
        "statement": "Return a + b.",
        "entry_point": "solve",
        "params": ["a", "b"],
        "tests": [
            {"input": {"a": 1, "b": 2}, "output": 3},
            {"input": {"a": -1, "b": 1}, "output": 0},
        ],
        "reference_solutions": {"python": ADD},
    }
    problem.update(overrides)
    return Problem.model_validate(problem)


def test_good_problem_passes():
    assert verify_problem(make_problem()).ok


def test_wrong_expected_output_is_caught():
    report = verify_problem(make_problem(tests=[{"input": {"a": 1, "b": 2}, "output": 4}]))
    assert not report.ok and "reference solution" in report.issues[0]


def test_wrong_example_is_caught():
    report = verify_problem(make_problem(examples=[{"input": {"a": 2, "b": 2}, "output": 5}]))
    assert any("example in the statement is wrong" in issue for issue in report.issues)


def test_answer_that_depends_on_set_order_is_caught():
    # The "expected" order is whatever hash seed 1 produces; seed 2 orders the set differently.
    words = (
        "def solve(a, b):\n    return list({'apple', 'banana', 'cherry', 'date', 'elder', 'fig'})\n"
    )
    probe = make_problem(
        reference_solutions={"python": words}, tests=[{"input": {"a": 0, "b": 0}, "output": None}]
    )
    seed_one_order = LocalRunner(hash_seed=1).run(probe, words).tests[0].output
    problem = make_problem(
        reference_solutions={"python": words},
        tests=[{"input": {"a": 0, "b": 0}, "output": seed_one_order}],
    )
    report = verify_problem(problem)
    assert not report.ok and "hash seed 2" in report.issues[0]


def test_mistake_that_no_test_catches_is_reported():
    # "a + b + 0" behaves exactly like the reference, so it is not a real, catchable mistake.
    mistake = {
        "description": "harmless rewrite",
        "python": "def solve(a, b):\n    return a + b + 0\n",
    }
    report = verify_problem(make_problem(common_mistakes=[mistake]))
    assert not report.ok and "passes every test" in report.issues[0]


def test_caught_mistake_records_its_tests():
    mistake = {"description": "subtracts", "python": "def solve(a, b):\n    return a - b\n"}
    report = verify_problem(make_problem(common_mistakes=[mistake]))
    assert report.ok and report.mistakes_caught_by == {0: [0, 1]}


def test_slow_solution_without_stress_test_is_reported():
    report = verify_problem(make_problem(slow_solutions={"python": ADD}))
    assert any("no stress test" in issue for issue in report.issues)


def test_slow_solution_that_is_not_slow_is_reported():
    stress = {"input": {"a": 5, "b": 5}, "output": 10, "stress": True}
    tests = [{"input": {"a": 1, "b": 2}, "output": 3}, stress]
    report = verify_problem(make_problem(tests=tests, slow_solutions={"python": ADD}))
    assert any("must time out on a stress test" in issue for issue in report.issues)
