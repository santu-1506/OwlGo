"""The shape of one problem file (problems/**/<id>.json).

Pydantic checks every file against these models, so a typo or a missing field
fails loudly instead of quietly producing bad training data. The full format,
with an example, is in docs/spec.json under data_schemas.problem.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from owlgo.problems.generators import GENERATORS

# Languages a problem can have signatures or solutions in.
Language = Literal["python", "cpp", "java", "javascript"]

# The 15 core DSA patterns, plus a few for simpler problems (from docs/spec.json).
Pattern = Literal[
    "arrays_and_hashing", "two_pointers", "sliding_window", "stack", "binary_search",
    "linked_list", "trees", "tries", "heap", "backtracking",
    "graphs_bfs_dfs", "dynamic_programming_1d", "dynamic_programming_2d", "greedy", "intervals",
    "basics", "math", "strings", "sorting", "bit_manipulation",
]  # fmt: skip


class _Strict(BaseModel):
    """Base for every model here: unknown fields are an error, so typos can't hide."""

    model_config = ConfigDict(extra="forbid")


class GeneratorSpec(_Strict):
    """A named, seeded generator that builds a large value (see generators.py)."""

    fn: str
    args: dict[str, Any] = {}

    @field_validator("fn")
    @classmethod
    def _known_generator(cls, fn: str) -> str:
        # Only generators that actually exist may be named.
        if fn not in GENERATORS:
            raise ValueError(f"unknown generator {fn!r}; known: {sorted(GENERATORS)}")
        return fn


class ProblemTest(_Strict):
    """One test case. Values use the tagged encoding from owlgo/values.py."""

    # Function problems: literal arguments by parameter name...
    input: dict[str, Any] = {}
    # ...and/or arguments built by a generator (for big stress inputs).
    generated_inputs: dict[str, GeneratorSpec] = {}
    # stdio problems: the text fed to standard input.
    stdin: str | None = None
    # The expected result: either a literal value or a generator for big outputs.
    output: Any = None
    generated_output: GeneratorSpec | None = None
    # True for tests that exist to catch slow solutions.
    stress: bool = False
    # Optional note on what the test checks, e.g. "empty input".
    purpose: str | None = None

    @model_validator(mode="after")
    def _exactly_one_expected_value(self):
        # "output": null is a valid expected value (a function returning None),
        # so check whether the field was given at all, not whether it is None.
        has_output = "output" in self.model_fields_set
        if has_output == (self.generated_output is not None):
            raise ValueError("a test needs exactly one of 'output' or 'generated_output'")
        return self


class Example(_Strict):
    """An example shown in the statement."""

    input: dict[str, Any]
    output: Any
    explanation: str | None = None


class Hint(_Strict):
    """One step of the hint ladder, from 1 (gentle nudge) to 4 (almost pseudocode)."""

    level: int = Field(ge=1, le=4)
    hint: str


class Optimal(_Strict):
    """The best known complexity and the name of the approach."""

    time: str
    space: str
    approach_name: str


class Suboptimal(_Strict):
    """A slower approach that is still fine as a first idea."""

    time: str
    note: str


class Mistake(_Strict):
    """A common mistake. The verification gate runs `python` and it must fail a test."""

    description: str
    python: str | None = None


class Comparison(_Strict):
    """How outputs are compared, following EvalPlus semantics."""

    # "exact" compares with ==; "set" turns both sides into sets first.
    mode: Literal["exact", "set"] = "exact"
    # Absolute tolerance for floats. 0 means exact, except float outputs get 1e-6.
    atol: float = 0.0


class Problem(_Strict):
    """One problem: statement, tests, solutions and teaching material."""

    # URL-safe slug that must match the file name, e.g. "longest-substring-no-repeat".
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str
    # Where it came from: "original", "evalplus/mbppplus", ...
    source: str
    source_url: str | None = None
    license: str
    difficulty: Literal["easy", "medium", "hard"]
    # "function": call a function, LeetCode style. "stdio": read stdin, write stdout.
    io_mode: Literal["function", "stdio"] = "function"
    # Empty for imported problems until Phase 2 tags them.
    patterns: list[Pattern] = []
    statement: str
    constraints: list[str] = []
    # Function problems: the function to call and its parameters, in order.
    entry_point: str | None = None
    params: list[str] = []
    function_signature: dict[Language, str] = {}
    examples: list[Example] = []
    tests: list[ProblemTest] = Field(min_length=1)
    comparison: Comparison = Comparison()
    # Correct solutions. Python is required; the verification gate runs it.
    reference_solutions: dict[Language, str]
    # Correct but too slow; must time out on a stress test.
    slow_solutions: dict[Language, str] = {}
    # Teaching material. Optional for imported problems until Phase 2 drafts it.
    optimal: Optimal | None = None
    acceptable_suboptimal: list[Suboptimal] = []
    hint_ladder: list[Hint] = []
    common_mistakes: list[Mistake] = []

    @model_validator(mode="after")
    def _check_consistency(self):
        # The verification gate needs a Python solution to run.
        if "python" not in self.reference_solutions:
            raise ValueError("reference_solutions must include python")
        if self.io_mode == "function":
            self._check_function_problem()
        else:
            self._check_stdio_problem()
        # Hint levels must go up one way: 1, 2, 3, 4 (gaps allowed, repeats not).
        levels = [hint.level for hint in self.hint_ladder]
        if levels != sorted(set(levels)):
            raise ValueError(f"hint_ladder levels must be unique and ascending, got {levels}")
        return self

    def _check_function_problem(self):
        if not self.entry_point:
            raise ValueError("function problems need an entry_point")
        if any(test.stdin is not None for test in self.tests):
            raise ValueError("function problems can't have stdin tests")
        # Every test and example must give the first k parameters (later ones may have defaults).
        given_inputs = [
            (f"test {i}", [*test.input, *test.generated_inputs])
            for i, test in enumerate(self.tests)
        ]
        given_inputs += [(f"example {i}", [*ex.input]) for i, ex in enumerate(self.examples)]
        for where, given in given_inputs:
            expected = self.params[: len(given)]
            if len(set(given)) != len(given) or set(given) != set(expected):
                raise ValueError(f"{where}: inputs {given} must be the first parameters {expected}")

    def _check_stdio_problem(self):
        if self.entry_point or self.params:
            raise ValueError("stdio problems have no entry_point or params")
        for i, test in enumerate(self.tests):
            if test.stdin is None or test.input or test.generated_inputs:
                raise ValueError(f"test {i}: stdio tests need stdin and no function inputs")
            if test.generated_output is None and not isinstance(test.output, str):
                raise ValueError(f"test {i}: stdio output must be the expected stdout text")

    @property
    def has_teaching_material(self) -> bool:
        """True once the problem has an optimal approach, hints and common mistakes."""
        return bool(self.optimal and self.hint_ladder and self.common_mistakes)
