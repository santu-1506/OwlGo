"""Load and validate problem files from the problems/ folder."""

from pathlib import Path

from pydantic import ValidationError

from owlgo.problems.schema import Problem

# problems/ at the repo root (this file is src/owlgo/problems/loader.py).
DEFAULT_PROBLEMS_DIR = Path(__file__).resolve().parents[3] / "problems"


class ProblemFileError(ValueError):
    """A problem file is invalid. The message starts with the file path."""


def load_problem(path: Path) -> Problem:
    """Read one problem file, validate it, and check its id matches the file name."""
    try:
        problem = Problem.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as error:
        raise ProblemFileError(f"{path}: {error}") from error
    # Keeping id == file name makes problems easy to find and impossible to duplicate.
    if problem.id != path.stem:
        raise ProblemFileError(f"{path}: id {problem.id!r} must match the file name")
    return problem


def problem_files(directory: Path = DEFAULT_PROBLEMS_DIR) -> list[Path]:
    """All problem files under directory, skipping anything starting with '_' (reports)."""
    return sorted(
        path
        for path in directory.rglob("*.json")
        if not any(part.startswith("_") for part in path.relative_to(directory).parts)
    )


def load_problems(directory: Path = DEFAULT_PROBLEMS_DIR) -> list[Problem]:
    """Load every problem under directory, failing on the first invalid or duplicate one."""
    problems: list[Problem] = []
    seen: dict[str, Path] = {}
    for path in problem_files(directory):
        problem = load_problem(path)
        # The same id in two folders would make train/test splits ambiguous.
        if problem.id in seen:
            other = seen[problem.id]
            raise ProblemFileError(f"{path}: duplicate id {problem.id!r} (also in {other})")
        seen[problem.id] = path
        problems.append(problem)
    return problems
