# 🦉 Owlgo

**Hoots hints, not answers.**

Owlgo is an open-source DSA practice companion. It sits beside the LeetCode editor in a Chrome side panel. It sees your problem, your code and your last failing test, and it helps only when you ask, only as much as you ask.

It is not a mock interviewer. There is no timer, no grading and no grilling. Think of it as a friend who is good at DSA sitting next to you while you practice.

> **Status:** Phase 0 (project setup) is done. Phase 1 (problem bank) is next. Nothing usable yet. See the [roadmap](#roadmap).

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
- **Small, local, private.** A fine-tuned small model running on your machine (Ollama first, in-browser WebLLM later). Free and offline.

## Ground rules

- **Off during contests.** Owlgo switches itself off on `leetcode.com/contest/*`. LeetCode's contest rules ban AI help.
- **Your data stays with you.** Page text and code go only to the model endpoint you configure, which is local by default. No analytics.
- **No LeetCode content in training.** Training and eval use original problems and open-licensed datasets (APPS, TACO) only.

## Roadmap

- [x] **Phase 0:** Project setup
- [ ] **Phase 1:** Problem bank and code runner (for training data only)
- [ ] **Phase 2:** Prompted baseline and evaluation (a score to beat)
- [ ] **Phase 3:** Training data (solver personas, bug injection)
- [ ] **Phase 4:** Fine-tuning and export to Ollama
- [ ] **Phase 5:** Chrome extension
- [ ] **Phase 6:** In-browser model, Hugging Face release, Chrome Web Store

The full plan lives in [docs/spec.json](docs/spec.json). It covers the help dial, intents, context block, bug injection, training, evaluation, the extension, and the commit list for every phase.

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

## License

[MIT](LICENSE)
