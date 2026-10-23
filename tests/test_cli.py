"""The terminal playground, driven with a scripted model instead of a real one."""

from owlgo.cli import Session, find_problem, main
from owlgo.llm_client import Reply


class ScriptedClient:
    def __init__(self, *texts):
        self.texts = list(texts)
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return Reply(self.texts.pop(0), "", "stop", 0, 0, 0.0)


def test_one_shot_question_prints_the_reply(capsys):
    client = ScriptedClient("Where is left when you reach the last 'a'?")
    main(["longest-substring-no-repeat", "--mistake", "0", "--ask", "why 3?"], client=client)
    assert "last 'a'" in capsys.readouterr().out
    # The model saw the real failing run of mistake 0.
    system = client.calls[0][0]["content"]
    assert "input: s = 'abba'" in system and "output: 3" in system


def test_session_remembers_only_what_the_user_saw():
    problem = find_problem("days-until-warmer")
    client = ScriptedClient("```python\nreturn []\n```", "Which day settles day 0?")
    session = Session(problem, problem.common_mistakes[0].python, 1, "prompted", client)
    reply = session.ask("help")
    assert reply.text == "Which day settles day 0?"
    # The code block the guard rejected never reaches the history.
    assert session.history[-1] == {"role": "assistant", "content": "Which day settles day 0?"}


def test_no_code_means_no_run():
    session = Session(find_problem("widest-container"), "", 1, "minimal", ScriptedClient())
    assert session.last_run is None
