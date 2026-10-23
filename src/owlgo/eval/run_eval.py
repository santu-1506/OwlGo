"""Run the model on every eval item and score its raw replies.

    uv run python -m owlgo.eval.run_eval                  # both prompt variants
    uv run python -m owlgo.eval.run_eval --variant prompted --limit 5

Replies are scored without the spoiler guard, because this measures the model itself.
Results go to eval/results/<model>-<variant>.jsonl and <model>-summary.json.
"""

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from owlgo.companion.context import context_for
from owlgo.companion.prompt import VARIANTS, build_messages
from owlgo.eval.metrics import score, summarize
from owlgo.eval.scenarios import build_items
from owlgo.llm_client import LLMClient
from owlgo.problems.loader import DEFAULT_PROBLEMS_DIR, load_problems

RESULTS_DIR = DEFAULT_PROBLEMS_DIR.parent / "eval" / "results"


def run(variants, limit=None, client=None, out_dir: Path = RESULTS_DIR) -> dict:
    """Evaluate each variant and write results. Returns {variant: summary}."""
    client = client or LLMClient()
    problems = {p.id: p for p in load_problems(DEFAULT_PROBLEMS_DIR / "original")}
    items = build_items(list(problems.values()))[:limit]
    model = re.sub(r"[^\w.-]+", "_", client.settings.model)
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for variant in variants:
        rows = []
        for number, item in enumerate(items, start=1):
            problem = problems[item.problem_id]
            context = context_for(problem, item.code, item.level, item.last_run)
            reply = client.chat(build_messages(context, item.user_message, variant=variant))
            row = {
                "id": item.id,
                "variant": variant,
                "intent": item.intent,
                "level": item.level,
                "user_message": item.user_message,
                "bug_lines": item.bug_lines,
                "last_run": asdict(item.last_run),
                "reply": reply.text,
                "finish_reason": reply.finish_reason,
                "seconds": round(reply.seconds, 2),
                "score": score(item, reply.text, problem),
            }
            rows.append(row)
            flag = (
                "SPOILER " + ",".join(row["score"]["violations"])
                if row["score"]["spoiler"]
                else "ok"
            )
            print(f"[{variant} {number}/{len(items)}] {item.id}: {row['score']['words']} words, "
                  f"{flag}, {reply.seconds:.1f}s", flush=True)  # fmt: skip
        with open(out_dir / f"{model}-{variant}.jsonl", "w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
        summaries[variant] = summarize(rows)
    summary_path = out_dir / f"{model}-summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2), flush=True)
    return summaries


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the companion on verified bugs.")
    parser.add_argument("--variant", choices=[*VARIANTS, "both"], default="both")
    parser.add_argument("--limit", type=int, help="only the first N items (for a quick check)")
    args = parser.parse_args(argv)
    variants = VARIANTS if args.variant == "both" else (args.variant,)
    run(variants, limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
