"""The verification gate: a problem enters the bank only if running it proves every claim in it.

Checks (docs/spec.json -> anti_hallucination.data_rules):
1. The reference solution passes every test, under two different hash seeds,
   so no expected answer depends on set or dict ordering.
2. The reference solution reproduces every example shown in the statement.
3. A slow solution passes every normal test and times out on a stress test,
   which proves the stress tests really catch slow code.
4. Every common mistake that has code fails at least one test, so every
   mistake the model learns about is real and catchable.

Run it on the whole bank with:  uv run python -m owlgo.problems.verify
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from owlgo.problems.loader import load_problems
from owlgo.problems.schema import Problem, ProblemTest
from owlgo.runner import LocalRunner, RunResult


@dataclass
class Verification:
    """The outcome of verifying one problem."""

    problem_id: str
    # Human-readable reasons the problem failed. Empty means it passed.
    issues: list[str] = field(default_factory=list)
    # Mistake index -> indexes of the tests that catch that mistake.
    mistakes_caught_by: dict[int, list[int]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.issues


def verify_problem(problem: Problem, per_test_seconds: float = 1.0) -> Verification:
    """Run every check on one problem and collect the issues found."""
    report = Verification(problem.id)
    reference = problem.reference_solutions["python"]
    runner = LocalRunner(per_test_seconds=per_test_seconds)

    # 1. The reference passes everything, under two hash seeds.
    for seed in (1, 2):
        result = LocalRunner(per_test_seconds=per_test_seconds, hash_seed=seed).run(
            problem, reference
        )
        if result.verdict != "accepted":
            report.issues.append(f"reference solution, hash seed {seed}: {describe(result)}")
            break

    # 2. The examples in the statement are true.
    if problem.examples:
        examples = [ProblemTest(input=ex.input, output=ex.output) for ex in problem.examples]
        result = runner.run(problem.model_copy(update={"tests": examples}), reference)
        if result.verdict != "accepted":
            report.issues.append(f"example in the statement is wrong: {describe(result)}")

    stress = [i for i, test in enumerate(problem.tests) if test.stress]
    normal = [i for i, test in enumerate(problem.tests) if not test.stress]

    # 3. The slow solution is correct but caught by a stress test.
    slow = problem.slow_solutions.get("python")
    if slow is not None:
        if not stress:
            report.issues.append("has a slow solution but no stress test to catch it")
        else:
            result = runner.run(problem, slow, only_tests=normal)
            if result.verdict != "accepted":
                report.issues.append(f"slow solution must pass normal tests: {describe(result)}")
            result = runner.run(problem, slow, only_tests=stress, stop_on_first_failure=True)
            if result.verdict != "time_limit_exceeded":
                report.issues.append(
                    f"slow solution must time out on a stress test, got {result.verdict}"
                )

    # 4. Every executable mistake is caught by at least one test.
    for k, mistake in enumerate(problem.common_mistakes):
        if mistake.python is None:
            continue
        result = runner.run(problem, mistake.python, only_tests=normal)
        caught = [t.index for t in result.tests if t.status != "passed"]
        # Some mistakes are only too slow, so only a stress test can catch them.
        if not caught and stress:
            result = runner.run(
                problem, mistake.python, only_tests=stress, stop_on_first_failure=True
            )
            caught = [t.index for t in result.tests if t.status not in ("passed", "not_run")]
        if caught:
            report.mistakes_caught_by[k] = caught
        else:
            report.issues.append(
                f"common mistake {k} ({mistake.description[:60]}) passes every test; "
                "add a test that catches it"
            )
    return report


def verify_problems(
    problems: list[Problem], per_test_seconds: float = 1.0, workers: int = 8
) -> list[Verification]:
    """Verify many problems in parallel (each run is its own process)."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda p: verify_problem(p, per_test_seconds), problems))


def describe(result: RunResult) -> str:
    """One line describing the first failing test of a run."""
    failure = result.first_failure
    text = f"test {failure.index} {failure.status}"
    if failure.status == "wrong_answer":
        text += f" (got {failure.output!r}, expected {failure.expected!r})"
    if failure.error:
        text += f": {failure.error}"
    return text[:300]


def main() -> int:
    """Verify the whole bank and print a summary. Exit code 1 if anything fails."""
    problems = load_problems()
    reports = verify_problems(problems)
    failed = [r for r in reports if not r.ok]
    for report in failed:
        print(f"FAIL {report.problem_id}")
        for issue in report.issues:
            print(f"     - {issue}")
    print(f"{len(reports) - len(failed)}/{len(reports)} problems verified")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
