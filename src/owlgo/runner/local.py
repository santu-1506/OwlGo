"""Run Python code against a problem's tests in a separate local process.

LocalRunner limits time per test and total CPU, but it is NOT a sandbox: the
code can still read files and use the network. Use it only for trusted code,
meaning our own solutions and well-known dataset reference solutions.
Untrusted code (model-written or scraped submissions) needs the sandboxed
runner planned for Phase 3.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from owlgo.problems.schema import Problem
from owlgo.runner.results import RunResult, TestResult

# Marker the harness puts in front of each result line (must match harness.py).
MARKER = "@@OWLGO@@ "

# Files copied into the run folder. They use only the standard library.
_SRC = Path(__file__).resolve().parents[1]
SUPPORT_FILES = {
    "harness.py": _SRC / "runner" / "harness.py",
    "values.py": _SRC / "values.py",
    "generators.py": _SRC / "problems" / "generators.py",
}

# Fields of a test the harness needs (stress and purpose are only notes for humans).
_TEST_FIELDS = {"input", "generated_inputs", "stdin", "output", "generated_output"}


class LocalRunner:
    """Runs code for one problem in a fresh Python process per run."""

    def __init__(
        self,
        per_test_seconds: float = 2.0,
        memory_mb: int = 512,
        hash_seed: int = 0,
        backstop_padding_seconds: float = 5.0,
    ):
        # Time allowed for each single test.
        self.per_test_seconds = per_test_seconds
        # Memory cap, enforced on Linux only (macOS ignores it).
        self.memory_mb = memory_mb
        # PYTHONHASHSEED for the run. Running twice with different seeds exposes tests
        # whose expected output depends on set or dict ordering.
        self.hash_seed = hash_seed
        # Extra seconds before the whole process is killed, in case it ignores the alarm.
        self.backstop_padding_seconds = backstop_padding_seconds

    def run(
        self,
        problem: Problem,
        code: str,
        *,
        stop_on_first_failure: bool = False,
        only_tests: list[int] | None = None,
    ) -> RunResult:
        """Run code against problem.tests (or just the tests listed in only_tests)."""
        indexes = [i for i in range(len(problem.tests)) if only_tests is None or i in only_tests]
        # The whole run is killed after this many seconds, no matter what.
        backstop = self.per_test_seconds * len(indexes) + self.backstop_padding_seconds
        payload = {
            "io_mode": problem.io_mode,
            "entry_point": problem.entry_point,
            "params": problem.params,
            "comparison": problem.comparison.model_dump(),
            "per_test_seconds": self.per_test_seconds,
            "stop_on_first_failure": stop_on_first_failure,
            "cpu_seconds": int(backstop) + 1,
            "memory_mb": self.memory_mb,
            "tests": [
                {"index": i, **problem.tests[i].model_dump(mode="json", include=_TEST_FIELDS)}
                for i in indexes
            ],
        }
        with tempfile.TemporaryDirectory(prefix="owlgo-run-") as folder:
            stdout, crash = self._execute(Path(folder), code, payload, backstop)
        return _collect_results(stdout, crash, indexes, stop_on_first_failure)

    def _execute(self, folder: Path, code: str, payload: dict, backstop: float):
        """Write the run folder, start the harness, and return (stdout, crash info)."""
        for name, source in SUPPORT_FILES.items():
            shutil.copyfile(source, folder / name)
        (folder / "solution.py").write_text(code, encoding="utf-8")
        (folder / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
        # -S: no site-packages, so the code sees only the standard library (like a judge).
        # -B: don't write .pyc files.
        command = [sys.executable, "-S", "-B", "harness.py", "payload.json"]
        env = {
            "PATH": os.defpath,
            "HOME": str(folder),
            "PYTHONHASHSEED": str(self.hash_seed),
            "PYTHONIOENCODING": "utf-8",
        }
        try:
            process = subprocess.run(
                command, cwd=folder, env=env, capture_output=True, text=True, timeout=backstop
            )
        except subprocess.TimeoutExpired as timeout:
            # Killed by the backstop: whatever was printed before that still counts.
            return _as_text(timeout.stdout), ("time_limit_exceeded", None)
        if process.returncode == 0:
            return process.stdout, None
        # The process died. SIGXCPU (signal 24, the CPU limit) counts as a timeout.
        if process.returncode == -24:
            return process.stdout, ("time_limit_exceeded", None)
        # Anything else is a crash; keep the last line of stderr as the explanation.
        last_line = (process.stderr.strip().splitlines() or [""])[-1][:300]
        error = f"process exited with code {process.returncode}: {last_line}"
        return process.stdout, ("runtime_error", error)


def _collect_results(stdout, crash, indexes, stop_on_first_failure) -> RunResult:
    """Turn the harness output into one TestResult per requested test."""
    reported: dict[int, dict] = {}
    load_failure = None
    for line in stdout.splitlines():
        if not line.startswith(MARKER):
            continue
        data = json.loads(line[len(MARKER) :])
        # index None means the code couldn't load at all, which fails every test.
        if data["index"] is None:
            load_failure = data
        else:
            reported[data["index"]] = data
    results = []
    stopped = False
    for i in indexes:
        if load_failure is not None:
            results.append(TestResult(**{**load_failure, "index": i}))
        elif i in reported:
            results.append(TestResult(**reported[i]))
            stopped = stopped or (stop_on_first_failure and reported[i]["status"] != "passed")
        elif not stopped and crash is not None:
            # The first test with no result is the one that was running when the process died.
            status, error = crash
            results.append(TestResult(index=i, status=status, error=error))
            stopped = True
        else:
            results.append(TestResult(index=i, status="not_run"))
    return RunResult(tests=results)


def _as_text(output) -> str:
    """TimeoutExpired can hold bytes even in text mode, so normalize to str."""
    if output is None:
        return ""
    return output.decode("utf-8", "replace") if isinstance(output, bytes) else output
