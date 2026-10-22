"""The schema must accept good problems and reject broken ones with a clear error."""

import json

import pytest
from pydantic import ValidationError

from owlgo.problems.loader import ProblemFileError, load_problem, load_problems
from owlgo.problems.schema import Problem


def make_problem(**overrides):
    """A small valid function problem; tests override fields to break it."""
    problem = {
        "id": "add-two",
        "title": "Add Two",
        "source": "original",
        "license": "MIT",
        "difficulty": "easy",
        "statement": "Return a + b.",
        "entry_point": "solve",
        "params": ["a", "b"],
        "tests": [{"input": {"a": 1, "b": 2}, "output": 3}],
        "reference_solutions": {"python": "def solve(a, b):\n    return a + b\n"},
    }
    problem.update(overrides)
    return problem


def test_valid_problem_loads():
    problem = Problem.model_validate(make_problem())
    assert problem.io_mode == "function" and not problem.has_teaching_material


def test_null_is_a_valid_expected_output():
    # A function returning None must be testable.
    Problem.model_validate(make_problem(tests=[{"input": {"a": 1, "b": 2}, "output": None}]))


BOTH_OUTPUTS = {"input": {"a": 1}, "output": 1, "generated_output": {"fn": "arange", "args": {}}}
BAD_GENERATOR = {"generated_inputs": {"a": {"fn": "no_such_generator"}}, "output": 1}
UNORDERED_HINTS = [{"level": 2, "hint": "b"}, {"level": 1, "hint": "a"}]


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"reference_solutions": {"cpp": "int solve();"}}, "must include python"),
        ({"tests": [{"input": {"b": 2}, "output": 3}]}, "must be the first parameters"),
        ({"tests": [{"input": {"a": 1, "b": 2}}]}, "exactly one of"),
        ({"tests": [BOTH_OUTPUTS]}, "exactly one of"),
        ({"tests": [BAD_GENERATOR]}, "unknown generator"),
        ({"entry_point": None}, "need an entry_point"),
        ({"id": "Bad ID"}, "should match pattern"),
        ({"surprise_field": 1}, "Extra inputs are not permitted"),
        ({"tests": []}, "at least 1 item"),
        ({"hint_ladder": UNORDERED_HINTS}, "unique and ascending"),
        ({"patterns": ["not_a_pattern"]}, "Input should be"),
    ],
)
def test_broken_problems_are_rejected(overrides, message):
    with pytest.raises(ValidationError, match=message):
        Problem.model_validate(make_problem(**overrides))


def test_stdio_problems_need_stdin_and_text_output():
    stdio = make_problem(
        io_mode="stdio", entry_point=None, params=[], tests=[{"stdin": "1 2\n", "output": "3\n"}]
    )
    Problem.model_validate(stdio)
    with pytest.raises(ValidationError, match="stdio tests need stdin"):
        Problem.model_validate({**stdio, "tests": [{"output": "3\n"}]})


def test_loader_checks_ids_and_skips_report_folders(tmp_path):
    # A valid file whose name matches its id loads fine.
    (tmp_path / "add-two.json").write_text(json.dumps(make_problem()))
    # Report folders start with '_' and must be ignored.
    (tmp_path / "_reports").mkdir()
    (tmp_path / "_reports" / "import.json").write_text("{}")
    assert [p.id for p in load_problems(tmp_path)] == ["add-two"]

    # A file named differently from its id is rejected.
    wrong_name = tmp_path / "other-name.json"
    wrong_name.write_text(json.dumps(make_problem()))
    with pytest.raises(ProblemFileError, match="must match the file name"):
        load_problem(wrong_name)


def test_loader_rejects_duplicate_ids(tmp_path):
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "add-two.json").write_text(json.dumps(make_problem()))
    with pytest.raises(ProblemFileError, match="duplicate id"):
        load_problems(tmp_path)
