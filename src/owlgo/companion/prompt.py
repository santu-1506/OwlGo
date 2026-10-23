"""Prompt variants and the message list sent to the model for one reply."""

from owlgo.companion.context import Context, render

# How many earlier chat messages the model sees (docs/spec.json -> context_block.history).
MAX_HISTORY_MESSAGES = 6

# Added after the context block in the "prompted" variant. The fine-tuned model gets the
# context block alone ("minimal"), because it learns this behaviour from training data.
BEHAVIOR_RULES = """## How to help
- Answer what the user actually asked, using their code, variable names and line numbers.
- Stay at or below the help level. If they want more, offer to turn the dial up instead.
- Be short: 1 to 3 sentences at levels 0 to 2, up to about 6 at level 3. No greetings or filler.
- Only state facts you can see in the code or the last run. If you are not sure, suggest an \
input to try instead of guessing.
- Never say the code is right or wrong without a run result.
- Praise only what is actually right, briefly and specifically.
- When an idea is wrong, give a counterexample or a question that exposes it.
- Below level 5 never show code. Below level 4 never list the steps of an algorithm. Below \
level 2 never name the algorithm or data structure, unless the user already used it."""

# "minimal": context block only. "prompted": context block plus BEHAVIOR_RULES.
VARIANTS = ("minimal", "prompted")


def system_prompt(context: Context, variant: str = "prompted") -> str:
    """The system message for a prompt variant."""
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}, got {variant!r}")
    block = render(context)
    return block if variant == "minimal" else f"{block}\n\n{BEHAVIOR_RULES}"


def build_messages(
    context: Context,
    user_message: str,
    history: list[dict] = (),
    variant: str = "prompted",
) -> list[dict]:
    """System prompt, the most recent chat history, then the new user message."""
    messages = [{"role": "system", "content": system_prompt(context, variant)}]
    messages += list(history)[-MAX_HISTORY_MESSAGES:]
    messages.append({"role": "user", "content": user_message})
    return messages
