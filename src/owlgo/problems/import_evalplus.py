"""Import MBPP+ and HumanEval+ (EvalPlus, Apache 2.0) into the problem bank.

Each EvalPlus row stores its tests as Python source: an `inputs = [...]` list,
a `results = [...]` list, and an `assertion(out, exp, atol)` function that
decides how outputs are compared. This module reads those parts with the ast
module (it never executes the test source), converts each problem to our
schema, and sends it through the verification gate. Anything we can't
reproduce exactly is skipped, and the reason goes into the import report.

Run:  uv run python -m owlgo.problems.import_evalplus
"""

import ast
import json
import re
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import ValidationError

from owlgo.problems.loader import DEFAULT_PROBLEMS_DIR
from owlgo.problems.schema import Problem
from owlgo.problems.verify import verify_problems
from owlgo.runner import LocalRunner
from owlgo.values import UnsupportedValue, encode

# Hugging Face's dataset viewer API: returns rows as JSON, no extra libraries needed.
ROWS_URL = "https://datasets-server.huggingface.co/rows?dataset={dataset}&config=default&split=test&offset={offset}&length=100"  # noqa: E501

DATASETS = {
    "mbpp": {
        "dataset": "evalplus/mbppplus",
        "license": "Apache-2.0 (EvalPlus); the original MBPP is CC-BY-4.0",
    },
    "humaneval": {
        "dataset": "evalplus/humanevalplus",
        "license": "Apache-2.0 (EvalPlus); the original HumanEval is MIT",
    },
}

# Keep tests small enough to show a model, and enough of them to catch bugs.
MAX_TESTS = 40
MAX_TEST_JSON_CHARS = 2000
MIN_TESTS = 3
# Tests the reference needs longer than this for are dropped, keeping a wide gap below
# the gate's timing margin so nothing is flaky on a slower machine.
HEAVY_TEST_MS = 100


class Skip(Exception):
    """This row can't be imported faithfully; the message says why."""


# --- Reading the test source --------------------------------------------------------------


def parse_test_source(source: str) -> dict:
    """Pull inputs, results, comparison mode and atol out of an EvalPlus test block."""
    tree = ast.parse(source)
    assigned = {
        node.targets[0].id: node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    if "inputs" not in assigned or "results" not in assigned:
        raise Skip("expected outputs are computed at test time, not stored")
    mode = _comparison_mode(source, tree)
    atol = _assertion_atol(tree)
    inputs = _literal(assigned["inputs"])
    results = _literal(assigned["results"])
    if len(inputs) != len(results):
        raise Skip("inputs and results have different lengths")
    return {"inputs": inputs, "results": results, "mode": mode, "atol": atol}


def _comparison_mode(source: str, tree: ast.Module) -> str:
    """'exact' or 'set', read from the assertion() helper. Anything unusual is skipped."""
    helper = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "assertion"),
        None,
    )
    if helper is None:
        raise Skip("no assertion() helper")
    body = re.sub(r"\s+", " ", ast.get_source_segment(source, helper))
    if "exp == (out is not None)" in body:
        raise Skip("custom comparison (checks only that a match exists)")
    if "out = set(out)" in body:
        return "set"
    if "np.allclose" in body and "==" in body:
        return "exact"
    raise Skip("unknown assertion() variant")


def _assertion_atol(tree: ast.Module) -> float:
    """The atol argument of the final `assertion(f(*inp), exp, atol)` call."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "assertion":
            expected_arg, atol_arg = node.args[1], node.args[2]
            # The expected value must come from the stored results, not from a helper.
            if not (isinstance(expected_arg, ast.Name) and expected_arg.id == "exp"):
                raise Skip("expected outputs are computed by a helper function")
            if not isinstance(atol_arg, ast.Constant):
                raise Skip("non-constant atol")
            return float(atol_arg.value)
    raise Skip("no assertion() call")


class _SpecialFloats(ast.NodeTransformer):
    """Rewrite `inf`, `nan` and float('inf') into constants so literal_eval accepts them."""

    def visit_Name(self, node):
        if node.id in ("inf", "nan"):
            return ast.copy_location(ast.Constant(float(node.id)), node)
        return node

    def visit_Call(self, node):
        if (
            getattr(node.func, "id", None) == "float"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            return ast.copy_location(ast.Constant(float(node.args[0].value)), node)
        return self.generic_visit(node)


def _literal(node: ast.AST):
    """Evaluate a literal expression safely (no code runs), allowing inf and nan."""
    try:
        return ast.literal_eval(_SpecialFloats().visit(node))
    except (ValueError, TypeError, SyntaxError, RecursionError) as error:
        raise Skip(f"test data is not a plain literal ({type(error).__name__})") from error


# --- Reading the function ------------------------------------------------------------------


def function_info(code: str, name: str) -> dict:
    """Parameters, signature line and docstring of the function `name` in code."""
    tree = ast.parse(code)
    function = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None
    )
    if function is None:
        raise Skip(f"function {name!r} not found at top level")
    args = function.args
    if args.vararg or args.kwarg or args.kwonlyargs:
        raise Skip("signature uses *args, **kwargs or keyword-only parameters")
    params = [a.arg for a in args.posonlyargs + args.args]
    returns = f" -> {ast.unparse(function.returns)}" if function.returns else ""
    return {
        "params": params,
        "signature": f"def {name}({ast.unparse(args)}){returns}:",
        "docstring": ast.get_docstring(function),
    }


# --- Building problems ---------------------------------------------------------------------


def build_tests(parsed: dict, params: list[str]) -> list[dict]:
    """Convert positional EvalPlus inputs into our named, encoded tests."""
    tests, seen = [], set()
    for args, result in zip(parsed["inputs"], parsed["results"], strict=True):
        if len(args) > len(params):
            continue
        # A test may give fewer arguments than there are parameters (the rest have defaults).
        named = zip(params[: len(args)], args, strict=True)
        try:
            test = {"input": {p: encode(a) for p, a in named}, "output": encode(result)}
        except UnsupportedValue:
            continue
        text = json.dumps(test, sort_keys=True)
        # Skip huge tests and exact duplicates.
        if len(text) > MAX_TEST_JSON_CHARS or text in seen:
            continue
        seen.add(text)
        tests.append(test)
        if len(tests) == MAX_TESTS:
            break
    if len(tests) < MIN_TESTS:
        raise Skip(f"only {len(tests)} usable tests (need {MIN_TESTS})")
    return tests


def mbpp_problem(row: dict) -> Problem:
    """One MBPP+ row -> Problem."""
    parsed = parse_test_source(row["test"])
    entry_point = _mbpp_entry_point(row["test"])
    code = row["code"].strip() + "\n"
    info = function_info(code, entry_point)
    return _problem(
        kind="mbpp",
        number=row["task_id"],
        entry_point=entry_point,
        statement=row["prompt"].strip(),
        signature=info["signature"],
        params=info["params"],
        reference=code,
        parsed=parsed,
    )


def humaneval_problem(row: dict) -> Problem:
    """One HumanEval+ row -> Problem."""
    parsed = parse_test_source(row["test"])
    entry_point = row["entry_point"]
    code = row["prompt"] + row["canonical_solution"]
    info = function_info(code, entry_point)
    if not info["docstring"]:
        raise Skip("no docstring to use as the statement")
    return _problem(
        kind="humaneval",
        number=row["task_id"].split("/")[1],
        entry_point=entry_point,
        statement=info["docstring"],
        signature=info["signature"],
        params=info["params"],
        reference=code,
        parsed=parsed,
    )


def drop_heavy_tests(problem: Problem) -> tuple[Problem, int]:
    """Remove tests the reference passes only slowly. Returns the problem and how many went.

    Tests the reference fails are kept on purpose, so the gate still rejects the problem
    instead of the failure being quietly hidden.
    """
    result = LocalRunner(per_test_seconds=5.0).run(problem, problem.reference_solutions["python"])
    heavy = {
        t.index for t in result.tests if t.status == "passed" and (t.time_ms or 0) > HEAVY_TEST_MS
    }
    if not heavy:
        return problem, 0
    kept = [test for i, test in enumerate(problem.tests) if i not in heavy]
    if len(kept) < MIN_TESTS:
        raise Skip(f"only {len(kept)} tests left after dropping slow ones")
    data = problem.model_dump(mode="json", exclude_unset=True)
    data["tests"] = [test.model_dump(mode="json", exclude_unset=True) for test in kept]
    data["examples"] = [{"input": t["input"], "output": t["output"]} for t in data["tests"][:2]]
    return Problem.model_validate(data), len(heavy)


def _mbpp_entry_point(test_source: str) -> str:
    """MBPP+ names the function only in the final call: assertion(name(*inp), exp, atol)."""
    match = re.search(r"assertion\((\w+)\(\*inp\)", test_source)
    if not match:
        raise Skip("can't find the function name in the test")
    return match.group(1)


def _problem(*, kind, number, entry_point, statement, signature, params, reference, parsed):
    tests = build_tests(parsed, params)
    slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", entry_point.lower())).strip("-")
    source = DATASETS[kind]
    try:
        return Problem.model_validate(
            {
                "id": f"{kind}-{number}-{slug}",
                "title": entry_point.replace("_", " ").strip().title(),
                "source": source["dataset"],
                "source_url": f"https://huggingface.co/datasets/{source['dataset']}",
                "license": source["license"],
                "difficulty": "easy",
                "statement": statement,
                "entry_point": entry_point,
                "params": params,
                "function_signature": {"python": signature},
                # The first two tests double as examples (the gate re-checks them).
                "examples": [{"input": t["input"], "output": t["output"]} for t in tests[:2]],
                "tests": tests,
                "comparison": {"mode": parsed["mode"], "atol": parsed["atol"]},
                "reference_solutions": {"python": reference},
            }
        )
    except ValidationError as error:
        raise Skip(f"does not fit the schema: {error.errors()[0]['msg']}") from error


# --- Fetching and writing ------------------------------------------------------------------


def fetch_rows(dataset: str) -> list[dict]:
    """Download every row of a dataset's test split, 100 rows per request."""
    rows, offset = [], 0
    while True:
        url = ROWS_URL.format(dataset=dataset, offset=offset)
        with urllib.request.urlopen(url, timeout=120) as response:
            page = json.load(response)
        for item in page["rows"]:
            # A truncated cell would silently lose tests, so refuse it.
            if item.get("truncated_cells"):
                raise RuntimeError(f"{dataset}: row {item['row_idx']} was truncated by the API")
            rows.append(item["row"])
        offset += 100
        if offset >= page["num_rows_total"]:
            return rows


def import_all(problems_dir: Path = DEFAULT_PROBLEMS_DIR) -> dict:
    """Fetch, convert, verify and write both datasets. Returns the import report."""
    builders = {"mbpp": mbpp_problem, "humaneval": humaneval_problem}
    report = {}
    for kind, build in builders.items():
        dataset = DATASETS[kind]["dataset"]
        rows = fetch_rows(dataset)
        built, dropped = [], []
        for row in rows:
            try:
                built.append(build(row))
            except Skip as reason:
                dropped.append({"task_id": str(row["task_id"]), "reason": str(reason)})
        # Drop slow tests (in parallel: each check is its own process).
        candidates, heavy_tests = [], 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(_try_drop_heavy_tests, built))
        for problem, outcome in zip(built, outcomes, strict=True):
            if isinstance(outcome, Skip):
                dropped.append({"task_id": problem.id, "reason": str(outcome)})
            else:
                candidates.append(outcome[0])
                heavy_tests += outcome[1]
        # Only problems that pass the verification gate are written.
        verified = []
        for problem, check in zip(candidates, verify_problems(candidates), strict=True):
            if check.ok:
                verified.append(problem)
            else:
                dropped.append({"task_id": problem.id, "reason": "gate: " + check.issues[0]})
        _write(problems_dir / "evalplus" / kind, verified)
        report[dataset] = {
            "rows": len(rows),
            "imported": len(verified),
            "slow_tests_removed": heavy_tests,
            "dropped": sorted(dropped, key=lambda d: d["task_id"]),
        }
        print(
            f"{dataset}: {len(verified)}/{len(rows)} imported, {len(dropped)} dropped, "
            f"{heavy_tests} slow tests removed"
        )
    report_path = problems_dir / "_reports" / "evalplus_import.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _try_drop_heavy_tests(problem: Problem):
    """drop_heavy_tests, but returning the Skip instead of raising (for pool.map)."""
    try:
        return drop_heavy_tests(problem)
    except Skip as reason:
        return reason


def _write(folder: Path, problems: list[Problem]) -> None:
    """Replace the folder's contents with one JSON file per problem."""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for problem in problems:
        # exclude_unset (not exclude_defaults): a test whose expected output is None must keep
        # its "output": null, or it would no longer validate.
        data = problem.model_dump(mode="json", exclude_unset=True)
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        (folder / f"{problem.id}.json").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    import_all()
