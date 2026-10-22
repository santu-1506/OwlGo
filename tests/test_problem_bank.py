"""Every problem in problems/ must load and pass the verification gate."""

import pytest

from owlgo.problems.loader import load_problems
from owlgo.problems.verify import verify_problems

PROBLEMS = load_problems()
ORIGINALS = [p for p in PROBLEMS if p.source == "original"]


@pytest.fixture(scope="module")
def reports():
    # Verify the whole bank once, in parallel, and share the results with every test below.
    return {report.problem_id: report for report in verify_problems(PROBLEMS)}


@pytest.mark.parametrize("problem", PROBLEMS, ids=lambda p: p.id)
def test_problem_passes_the_gate(problem, reports):
    report = reports[problem.id]
    assert report.ok, "\n".join(report.issues)


@pytest.mark.parametrize("problem", ORIGINALS, ids=lambda p: p.id)
def test_hand_written_problems_have_full_teaching_material(problem):
    # Hand-written problems are the gold standard for the test split, so nothing may be missing.
    assert problem.has_teaching_material
    assert [h.level for h in problem.hint_ladder] == [1, 2, 3, 4]
    assert all(m.python for m in problem.common_mistakes), "every mistake needs runnable code"
    assert "python" in problem.slow_solutions
    assert any(test.stress for test in problem.tests)
    assert set(problem.function_signature) == {"python", "cpp", "java", "javascript"}


def test_bank_has_the_hand_written_problems():
    assert len(ORIGINALS) >= 5
