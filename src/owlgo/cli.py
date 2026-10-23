"""Terminal playground: chat with Owlgo about a problem from the bank.

    uv run python -m owlgo.cli longest-substring-no-repeat --code my_solution.py --level 1
    uv run python -m owlgo.cli longest-substring-no-repeat --mistake 0 --ask "why is it 3?"

--mistake N uses the problem's verified common mistake N as your code, which is a
quick way to see how Owlgo handles a real bug.

Inside the chat:
    /level N    change the help level (0 to 5)
    /run        re-run your code file and refresh the last run
    /context    show exactly what the model sees
    /quit       leave
"""

import argparse
import sys
from pathlib import Path

from owlgo.companion.context import LastRun, context_for, last_run_from_result
from owlgo.companion.guard import GuardedReply, guarded_chat
from owlgo.companion.prompt import VARIANTS, build_messages, system_prompt
from owlgo.llm_client import LLMClient
from owlgo.problems.loader import DEFAULT_PROBLEMS_DIR, load_problem
from owlgo.problems.schema import Problem
from owlgo.runner import LocalRunner


class Session:
    """One chat about one problem: the code, the help level and the history so far."""

    def __init__(self, problem: Problem, code: str, level: int, variant: str, client):
        self.problem = problem
        self.code = code
        self.level = level
        self.variant = variant
        self.client = client
        self.history: list[dict] = []
        self.last_run = self.run_code()

    def run_code(self) -> LastRun | None:
        """Run the current code against the problem's tests, like pressing Run."""
        if not self.code.strip():
            return None
        result = LocalRunner().run(self.problem, self.code, stop_on_first_failure=True)
        return last_run_from_result(self.problem, result)

    def context(self):
        return context_for(self.problem, self.code, self.level, self.last_run)

    def ask(self, question: str) -> GuardedReply:
        """Send one question through the guard and remember the exchange."""
        messages = build_messages(self.context(), question, self.history, self.variant)
        reply = guarded_chat(
            self.client, messages, self.level, self.problem, user_text=question, code=self.code
        )
        # History keeps only what the user actually saw.
        self.history += [
            {"role": "user", "content": question},
            {"role": "assistant", "content": reply.text},
        ]
        return reply


def find_problem(problem_id: str) -> Problem:
    """Load a problem by id from anywhere in the bank."""
    matches = list(DEFAULT_PROBLEMS_DIR.rglob(f"{problem_id}.json"))
    if not matches:
        sys.exit(f"no problem with id {problem_id!r} (problem files are in {DEFAULT_PROBLEMS_DIR})")
    return load_problem(matches[0])


def describe(reply: GuardedReply) -> str:
    """The reply, plus a short note when the guard had to step in."""
    if reply.used_fallback:
        return f"{reply.text}\n  [guard: both tries gave too much help, sent a safe reply]"
    if len(reply.replies) > 1:
        broken = ", ".join(v.check for v in reply.violations[0])
        return f"{reply.text}\n  [guard: first reply broke {broken}, regenerated]"
    return reply.text


def main(argv: list[str] | None = None, client=None) -> int:
    parser = argparse.ArgumentParser(description="Chat with Owlgo about a problem.")
    parser.add_argument("problem", help="problem id, e.g. longest-substring-no-repeat")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--code", type=Path, help="your solution file (Python)")
    source.add_argument("--mistake", type=int, help="use the problem's common mistake N as code")
    parser.add_argument("--level", type=int, default=1, choices=range(6), help="help level 0-5")
    parser.add_argument("--variant", choices=VARIANTS, default="prompted")
    parser.add_argument("--ask", help="ask one question, print the reply and exit")
    args = parser.parse_args(argv)

    problem = find_problem(args.problem)
    code = ""
    if args.code:
        code = args.code.read_text(encoding="utf-8")
    elif args.mistake is not None:
        code = problem.common_mistakes[args.mistake].python or ""
    session = Session(problem, code, args.level, args.variant, client or LLMClient())

    if args.ask:
        print(describe(session.ask(args.ask)))
        return 0

    status = session.last_run.status if session.last_run else "not run"
    print(f"Owlgo · {problem.title} · help level {session.level} · last run: {status}")
    print("Commands: /level N, /run, /context, /quit\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text in ("/quit", "/exit"):
            return 0
        if text == "/context":
            print(system_prompt(session.context(), session.variant), "\n")
        elif text == "/run":
            if args.code:
                session.code = args.code.read_text(encoding="utf-8")
            session.last_run = session.run_code()
            print(f"last run: {session.last_run.status if session.last_run else 'not run'}\n")
        elif text.startswith("/level"):
            parts = text.split()
            if len(parts) == 2 and parts[1].isdigit() and 0 <= int(parts[1]) <= 5:
                session.level = int(parts[1])
                print(f"help level is now {session.level}\n")
            else:
                print("usage: /level N, with N from 0 to 5\n")
        else:
            print(f"owlgo> {describe(session.ask(text))}\n")


if __name__ == "__main__":
    sys.exit(main())
