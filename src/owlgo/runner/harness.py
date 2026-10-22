"""Runs one solution against a list of tests. Executed as a script, never imported.

Usage: python harness.py payload.json

The runner copies this file, values.py, generators.py and the code under test
(solution.py) into an empty temp folder and runs this script there. Each
finished test prints one line on stdout:

    @@OWLGO@@ {"index": 0, "status": "passed", "time_ms": 0.01}

The marker separates our result lines from anything the solution prints.
Lines are flushed one at a time, so if the process is killed mid-way, the
runner still knows which tests finished.

Standard library only: this must run with no packages installed.
"""

import contextlib
import io
import json
import resource
import signal
import sys
import time
import traceback

# Both files are copied next to this script by the runner.
from generators import generate
from values import decode, encode_or_repr

MARKER = "@@OWLGO@@ "
SOLUTION_FILE = "solution.py"


class TimeLimit(BaseException):
    """Raised by the alarm when a test runs too long.

    It subclasses BaseException, so a solution's `except Exception:` can't swallow it.
    """


def main():
    with open(sys.argv[1], encoding="utf-8") as file:
        payload = json.load(file)
    with open(SOLUTION_FILE, encoding="utf-8") as file:
        code = file.read()
    # Limits go on before any solution code runs.
    apply_limits(payload["cpu_seconds"], payload["memory_mb"])
    # SIGALRM ends a single test that runs past its time limit.
    signal.signal(signal.SIGALRM, on_alarm)
    if payload["io_mode"] == "function":
        run_function_tests(code, payload)
    else:
        run_stdio_tests(code, payload)


def apply_limits(cpu_seconds, memory_mb):
    """Cap total CPU time and (on Linux) memory for this whole process."""
    # Past the soft limit the OS sends SIGXCPU, which kills the process.
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    # macOS does not enforce address-space limits, so memory is capped on Linux only.
    if sys.platform.startswith("linux"):
        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def on_alarm(signum, frame):
    raise TimeLimit()


def run_function_tests(code, payload):
    """Function mode: define the solution once, then call it once per test."""
    namespace = {"__name__": "solution"}
    try:
        # Compiling with the file name "solution.py" makes tracebacks point at its lines.
        exec(compile(code, SOLUTION_FILE, "exec"), namespace)
    except BaseException as exc:
        # A syntax error, or a crash while the code was being defined.
        emit_load_failure(exc)
        return
    function = namespace.get(payload["entry_point"])
    if not callable(function):
        error = f"function {payload['entry_point']!r} is not defined"
        emit({"index": None, "status": "compile_error", "error": error})
        return
    for test in payload["tests"]:
        # Build arguments and the expected value before the clock starts.
        args = build_args(test, payload["params"])
        expected = expected_value(test)
        result = run_one(lambda args=args: function(*args), payload["per_test_seconds"])
        printed = result.pop("printed")
        if printed:
            result["stdout"] = printed[:1000]
        if result["status"] == "finished":
            output = result.pop("value")
            matched = outputs_match(output, expected, payload["comparison"])
            result["status"] = "passed" if matched else "wrong_answer"
            result["output"] = encode_or_repr(output)
        report(test, result, expected)
        if payload["stop_on_first_failure"] and result["status"] != "passed":
            return


def run_stdio_tests(code, payload):
    """stdio mode: run the whole program once per test, with that test's stdin."""
    try:
        compiled = compile(code, SOLUTION_FILE, "exec")
    except SyntaxError as exc:
        emit_load_failure(exc)
        return
    for test in payload["tests"]:
        expected = expected_value(test)
        program = lambda test=test: run_program(compiled, test["stdin"])  # noqa: E731
        result = run_one(program, payload["per_test_seconds"])
        # In stdio mode, what the program printed IS its answer.
        printed = result.pop("printed")
        if result["status"] == "finished":
            result.pop("value")
            matched = normalize_text(printed) == normalize_text(expected)
            result["status"] = "passed" if matched else "wrong_answer"
            result["output"] = printed[:2000]
        elif printed:
            result["stdout"] = printed[:1000]
        report(test, result, expected)
        if payload["stop_on_first_failure"] and result["status"] != "passed":
            return


def run_program(compiled, stdin_text):
    """Run a whole stdio program with stdin_text as its standard input."""
    old_stdin = sys.stdin
    # A real text wrapper over bytes, so solutions can use sys.stdin.buffer too.
    sys.stdin = io.TextIOWrapper(io.BytesIO(stdin_text.encode("utf-8")), encoding="utf-8")
    try:
        exec(compiled, {"__name__": "__main__"})
    except SystemExit as exc:
        # exit() or sys.exit(0) is a normal way to finish; any other code is an error.
        if exc.code not in (None, 0):
            raise RuntimeError(f"program exited with code {exc.code}") from exc
    finally:
        sys.stdin = old_stdin


def run_one(call, seconds):
    """Run call() with a time limit while capturing prints.

    Returns {"status": "finished", "value": ...} or a failure status, plus the
    captured text under "printed" and the time taken under "time_ms".
    """
    captured = io.StringIO()
    start = time.perf_counter()
    # One-shot timer: SIGALRM fires once after `seconds`.
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        with contextlib.redirect_stdout(captured):
            value = call()
        # Stop the clock before comparing, so a slow comparison never counts as a timeout.
        signal.setitimer(signal.ITIMER_REAL, 0)
        result = {"status": "finished", "value": value}
    except TimeLimit:
        result = {"status": "time_limit_exceeded"}
    except MemoryError:
        result = {"status": "memory_limit_exceeded"}
    except BaseException as exc:
        result = {"status": "runtime_error", "error": describe(exc), "error_line": error_line(exc)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    result["time_ms"] = round((time.perf_counter() - start) * 1000, 3)
    result["printed"] = captured.getvalue()
    return result


def report(test, result, expected):
    """Print one test result. The expected value is included only for failures."""
    result["index"] = test["index"]
    if result["status"] != "passed":
        result["expected"] = encode_or_repr(expected)
    emit(result)


def emit_load_failure(exc):
    """Report code that could not even be loaded. It applies to every test."""
    if isinstance(exc, SyntaxError):
        emit({"index": None, "status": "compile_error", "error": describe(exc),
              "error_line": exc.lineno})  # fmt: skip
    else:
        emit({"index": None, "status": "runtime_error", "error": describe(exc),
              "error_line": error_line(exc)})  # fmt: skip


def build_args(test, params):
    """Decode a test's arguments and put them in the function's parameter order."""
    values = {name: decode(value) for name, value in test["input"].items()}
    for name, spec in test["generated_inputs"].items():
        values[name] = generate(spec["fn"], spec["args"])
    return [values[name] for name in params if name in values]


def expected_value(test):
    """The decoded expected output, built by its generator if it has one."""
    spec = test.get("generated_output")
    if spec is not None:
        return generate(spec["fn"], spec["args"])
    return decode(test["output"])


def outputs_match(output, expected, comparison):
    """Compare like EvalPlus: exact ==, optional set mode, float tolerance."""
    if comparison["mode"] == "set":
        try:
            output, expected = set(output), set(expected)
        except TypeError:
            return False
    atol = comparison["atol"]
    # EvalPlus rule: float outputs get a small tolerance even when atol is 0.
    if atol == 0 and is_floats(expected):
        atol = 1e-6
    try:
        if output == expected:
            return True
    except Exception:
        return False
    return atol != 0 and close(output, expected, atol)


def is_floats(value):
    """A float, or a list/tuple made only of floats (the EvalPlus definition)."""
    if isinstance(value, float):
        return True
    if isinstance(value, (list, tuple)):
        return all(isinstance(item, float) for item in value)
    return False


def close(output, expected, atol, rtol=1e-7):
    """numpy.allclose for numbers and nested lists/tuples of numbers."""
    if isinstance(output, (int, float)) and isinstance(expected, (int, float)):
        return output == expected or abs(output - expected) <= atol + rtol * abs(expected)
    if isinstance(output, (list, tuple)) and isinstance(expected, (list, tuple)):
        return len(output) == len(expected) and all(
            close(o, e, atol, rtol) for o, e in zip(output, expected, strict=True)
        )
    return False


def normalize_text(text):
    """Ignore trailing spaces and trailing blank lines, like most online judges."""
    return "\n".join(line.rstrip() for line in text.rstrip().splitlines())


def error_line(exc):
    """Line in solution.py where the exception happened (deepest such frame), or None."""
    frames = traceback.extract_tb(exc.__traceback__)
    lines = [frame.lineno for frame in frames if frame.filename == SOLUTION_FILE]
    return lines[-1] if lines else None


def describe(exc):
    """Short 'Type: message' text for an exception."""
    return f"{type(exc).__name__}: {exc}"[:500]


def emit(result):
    """Write one marked result line to the real stdout and flush it immediately."""
    sys.__stdout__.write(MARKER + json.dumps(result) + "\n")
    sys.__stdout__.flush()


if __name__ == "__main__":
    main()
