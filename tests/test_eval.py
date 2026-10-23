"""Eval items carry real ground truth, and the metrics read replies correctly."""

import json

from owlgo.eval.metrics import cited_lines, score, summarize
from owlgo.eval.run_eval import run
from owlgo.eval.scenarios import bug_lines, build_items
from owlgo.llm_client import LLMSettings, Reply
from owlgo.problems.loader import DEFAULT_PROBLEMS_DIR, load_problems

PROBLEMS = {p.id: p for p in load_problems(DEFAULT_PROBLEMS_DIR / "original")}
ITEMS = {item.id: item for item in build_items(list(PROBLEMS.values()))}
ABBA = ITEMS["longest-substring-no-repeat-m0-L1"]


def test_items_cover_every_mistake_and_level():
    # 15 verified mistakes x 4 levels, plus one "give me the code" per problem.
    assert len(ITEMS) == 15 * 4 + 5


def test_items_carry_the_real_failing_run_and_bug_line():
    run_ = ABBA.last_run
    assert (run_.status, run_.input, run_.expected, run_.output) == (
        "wrong_answer",
        "s = 'abba'",
        "2",
        "3",
    )
    assert ABBA.bug_lines == [6]
    # Approach-level bugs have no single line.
    assert ITEMS["longest-consecutive-run-m1-L0"].bug_lines is None


def test_bug_lines():
    assert bug_lines("a\nb\nc", "a\nB\nc") == [2]
    assert bug_lines("a\nb\nc\nd\ne", "1\n2\n3\n4\n5") is None


def test_cited_lines():
    assert cited_lines("Look at line 6.") == {6}
    assert cited_lines("Lines 5-7 and line 10") == {5, 6, 7, 10}
    assert cited_lines("No line numbers here, just index 2.") == set()


def test_score_spots_right_and_wrong_lines():
    problem = PROBLEMS["longest-substring-no-repeat"]
    right = score(ABBA, "What does line 6 do when you reach the last 'a' in 'abba'?", problem)
    assert right["right_line"] and right["uses_failing_input"] and not right["spoiler"]
    wrong = score(ABBA, "Check line 9.", problem)
    assert wrong["wrong_line"] and not wrong["uses_failing_input"]
    praise = score(ABBA, "Your logic is correct, great job!", problem)
    assert praise["false_praise"]
    leak = score(ABBA, "```python\nreturn 2\n```", problem)
    assert leak["spoiler"] and leak["violations"] == ["code_block"]


class ScriptedClient:
    settings = LLMSettings(model="scripted")

    def chat(self, messages):
        return Reply("Which value does left have on line 7 at the last 'a'?", "", "stop", 0, 0, 1.0)


def test_run_writes_results_and_summary(tmp_path):
    summaries = run(["minimal"], limit=3, client=ScriptedClient(), out_dir=tmp_path)
    rows = [
        json.loads(line) for line in (tmp_path / "scripted-minimal.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 3 and rows[0]["reply"].startswith("Which value")
    assert summaries["minimal"]["items"] == 3
    assert (tmp_path / "scripted-summary.json").exists()


def test_summarize_handles_no_line_citations():
    rows = [{"intent": "debug", "level": 1, "seconds": 1.0,
             "score": {"spoiler": False, "too_long": False, "right_line": None,
                       "uses_failing_input": True, "false_praise": False, "empty": False,
                       "words": 10}}]  # fmt: skip
    summary = summarize(rows)
    assert summary["line_accuracy"] is None and summary["uses_failing_input_rate"] == 100.0
