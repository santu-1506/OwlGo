"""Results of running code against a problem's tests."""

from typing import Any, Literal

from pydantic import BaseModel

# Per-test outcomes. "not_run" means the run stopped before reaching this test.
Status = Literal[
    "passed",
    "wrong_answer",
    "time_limit_exceeded",
    "memory_limit_exceeded",
    "runtime_error",
    "compile_error",
    "not_run",
]


class TestResult(BaseModel):
    """What happened on one test. Values use the tagged encoding from owlgo/values.py."""

    # Tell pytest this is not a test class, despite its name.
    __test__ = False

    # Position of the test in problem.tests.
    index: int
    status: Status
    time_ms: float | None = None
    # What the code returned (or printed, in stdio mode).
    output: Any = None
    # Included for failed tests only.
    expected: Any = None
    # Exception text and the line of solution.py it came from.
    error: str | None = None
    error_line: int | None = None
    # Anything the code printed (function mode).
    stdout: str | None = None


class RunResult(BaseModel):
    """All test results of one run, in test order."""

    tests: list[TestResult]

    @property
    def first_failure(self) -> TestResult | None:
        """The first test that did not pass, or None if all passed."""
        return next((t for t in self.tests if t.status != "passed"), None)

    @property
    def verdict(self) -> str:
        """'accepted', or the status of the first failing test (like LeetCode's verdict)."""
        failure = self.first_failure
        return "accepted" if failure is None else failure.status

    @property
    def passed_count(self) -> int:
        return sum(t.status == "passed" for t in self.tests)
