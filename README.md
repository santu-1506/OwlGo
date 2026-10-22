# 🦉 Owlgo

**Hoots hints, not answers.**

Owlgo is an open-source DSA practice companion. It sits beside the LeetCode editor in a Chrome side panel. It sees your problem, your code and your last failing test, and it helps only when you ask, only as much as you ask.

It is not a mock interviewer. There is no timer, no grading and no grilling. Think of it as a friend who is good at DSA sitting next to you while you practice.

> **Status:** Phase 1 is done: 534 verified problems and a code runner. Phase 2 (prompted baseline and evaluation) is in progress. See the [roadmap](#roadmap).

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
