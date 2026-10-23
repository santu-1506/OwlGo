# 🦉 Owlgo

**Hoots hints, not answers.**

Owlgo is an open-source DSA practice companion. It sits beside the LeetCode editor in a Chrome side panel. It sees your problem, your code and your last failing test, and it helps only when you ask, only as much as you ask.

It is not a mock interviewer. There is no timer, no grading and no grilling. Think of it as a friend who is good at DSA sitting next to you while you practice.

> **Status:** Phase 1 is done: 534 verified problems and a code runner. Phase 2 is in progress: the companion pipeline works end to end and the [Qwen3.5-9B baseline](#baseline-qwen35-9b-before-any-training) is recorded. See the [roadmap](#roadmap).

## The Help Dial

You choose how much help you want. Owlgo is trained to stay exactly at that level.

| Level | Name | What Owlgo does |
|---|---|---|
| 0 | Rubber duck | Only asks questions and reflects back what you said |
| 1 | Nudge | One question that points where to look |
| 2 | Hint | Names the idea or data structure, or points at the buggy region |
| 3 | Approach | Explains the key insight in plain words, no code |
| 4 | Pseudocode | Step-by-step outline, no runnable code |
| 5 | Solution | Full or fixed code (asks you to confirm first) |

## What makes it different

- **It reads your context.** Problem, code, language and the last Run result, so it helps with *your* bug, not a generic one.
- **Bug-injection training data.** Real bugs are added to correct solutions and verified by actually running them. That lets us measure whether the model points at the right line.
- **Grounded, not guessed.** Every fact Owlgo learns from is verified by running code. Tests, bugs and "this input breaks your code" claims are all checked by execution.
- **A small fine-tuned model on your own machine.** Qwen3.5-9B, fine-tuned, running through Ollama: free, private and offline. A hosted API may come later.

## Ground rules

- **Off during contests.** Owlgo switches itself off on `leetcode.com/contest/*`. LeetCode's contest rules ban AI help.
- **Your data stays with you.** Page text and code go only to the model on your own machine. No analytics.
- **No LeetCode content in training.** Training and eval use original problems and permissively licensed datasets only (APPS, TACO without its LeetCode/GFG/HackerRank parts, CodeContests).

## Roadmap

- [x] **Phase 0:** Project setup
- [x] **Phase 1:** Problem bank and code runner, assembled from verified open data
- [ ] **Phase 2:** Prompted baseline and evaluation (a score to beat)
- [ ] **Phase 3:** Training data (solver personas, bug injection)
- [ ] **Phase 4:** Fine-tuning and export to Ollama
- [ ] **Phase 5:** Chrome extension
- [ ] **Phase 6:** In-browser model, Hugging Face release, Chrome Web Store

The full plan lives in [docs/spec.json](docs/spec.json). It covers the help dial, intents, context block, bug injection, training, evaluation, the extension, and the commit list for every phase.

## Problem bank

Problems live in `problems/`, one JSON file each. The format is `data_schemas.problem` in [docs/spec.json](docs/spec.json). A problem only gets in if the **verification gate** proves everything in it by running code:

1. The correct solution passes every test, twice, under two different hash seeds.
2. Every example shown in the statement is correct.
3. The slow solution passes the normal tests but times out on a stress test.
4. Every listed common mistake is real code that fails at least one test.

```bash
uv run python -m owlgo.problems.verify   # verify the whole bank
```

| Folder | Problems | Source |
|---|---|---|
| `problems/original/` | 5 | Hand-written, LeetCode-style, with full hints and executable mistakes. Reserved for the test split. |
| `problems/evalplus/mbpp/` | 372 | [MBPP+](https://huggingface.co/datasets/evalplus/mbppplus) (Apache 2.0; MBPP is CC BY 4.0) |
| `problems/evalplus/humaneval/` | 157 | [HumanEval+](https://huggingface.co/datasets/evalplus/humanevalplus) (Apache 2.0; HumanEval is MIT) |

Imported problems have no hints or pattern tags yet; Phase 2 drafts them with a strong model and verifies them by execution. To re-import (about 4 MB download, under a minute):

```bash
uv run python -m owlgo.problems.import_evalplus
```

Every skipped problem and the reason is listed in [problems/_reports/evalplus_import.json](problems/_reports/evalplus_import.json). The gate also requires the reference to use under 25% of the time limit per test, so tests that are slow even for the correct answer are removed rather than left to be flaky.

## Baseline: Qwen3.5-9B before any training

65 scenarios built from the 15 verified bugs in the hand-written problems: each bug's real failing run, asked about at help levels 0 to 3, plus one "just give me the fixed code" per problem. Scored by rules and by running code, with no judge model yet. Raw replies are in [eval/results/](eval/results/).

| Metric | Minimal prompt | With written rules | Target |
|---|---|---|---|
| Replies breaking the help level (code, steps, naming the technique) | 24.6% | **6.2%** | under 2% |
| "Just give me the code" leaks | 60% | 20% | 0% |
| Mean words, levels 0 to 2 | 96 | 65 | 10 to 45 |
| Replies over the length limit | 58.5% | 33.8% | |
| Cited line holds the bug (when a line is cited) | 38.5% (5/13) | 75% (18/24) | |
| Uses the real failing input | 36.7% | 43.3% | |
| False praise | 1.5% | 0% | under 3% |
| Seconds per reply on a 16 GB M4 | 16.5 | 13.0 | |

What this shows:
- **Written rules help a lot but don't get there.** One in 16 replies still breaks the help level, and level-0 replies average 79 words when they should be a single question.
- **Confident claims are often false.** Two test inputs Qwen suggested ("try `[50, 49]`", "try `'abcdebfge'`") were run on the buggy code, and both pass, so they would not show the student anything. One of them came from a reply that pointed at the right line.
- **The line metric is only a proxy.** It misses replies that point at an equally valid fix location, and it counts replies that cite correct lines for context. The judge model and an execution check of suggested inputs come next.

Reproduce: `uv run python -m owlgo.eval.run_eval` (Ollama running with `qwen3.5:9b`, about 30 minutes).

## Development

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# Create the virtual env and install dev tools (pytest, ruff)
uv sync

# Lint, check formatting, and run the tests
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

### macOS: "No module named 'owlgo'"

Some Macs set the hidden flag on everything inside `.venv`. Python 3.11.15 and newer skip hidden `.pth` files, so the editable install disappears. Check with `ls -lO .venv/lib/python3.11/site-packages/*.pth`. If the flags column says `hidden`, keep the real environment in `venv/` and link `.venv` to it:

```bash
rm -rf .venv
UV_PROJECT_ENVIRONMENT=venv uv sync
ln -s venv .venv
```

## License

[MIT](LICENSE)
