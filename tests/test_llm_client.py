"""The model client: config, hidden-reasoning handling, and the request it sends."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer

import pytest

from owlgo.config import LLMSettings
from owlgo.llm_client import LLMClient, split_thinking


def test_split_thinking():
    assert split_thinking("Hello") == ("Hello", "")
    assert split_thinking("<think>plan</think>\nHi there") == ("Hi there", "plan")
    # Cut off while thinking: nothing after the open tag may be shown.
    assert split_thinking("Hi <think>secret plan") == ("Hi", "secret plan")


def test_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("OWLGO_LLM_MODEL", "other-model")
    monkeypatch.setenv("OWLGO_LLM_TEMPERATURE", "0.9")
    monkeypatch.setenv("OWLGO_LLM_MAX_TOKENS", "50")
    settings = LLMSettings.from_env()
    assert (settings.model, settings.temperature, settings.max_tokens) == ("other-model", 0.9, 50)
    assert settings.base_url == "http://localhost:11434/v1"


@pytest.fixture
def fake_server():
    """A tiny OpenAI-compatible server that records requests and returns a canned reply."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            reply = {
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "<think>hmm</think>Look at line 6.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
            }
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass  # keep test output clean

    # Plain TCPServer, not HTTPServer: HTTPServer does a reverse DNS lookup at startup
    # that takes about 35 seconds on some Macs.
    server = TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1", requests
    server.shutdown()


def test_client_sends_settings_and_hides_thinking(fake_server):
    base_url, requests = fake_server
    client = LLMClient(LLMSettings(base_url=base_url, model="test-model", max_tokens=99))
    reply = client.chat([{"role": "user", "content": "why?"}])
    assert reply.text == "Look at line 6." and reply.thinking == "hmm"
    assert (reply.prompt_tokens, reply.completion_tokens, reply.finish_reason) == (12, 5, "stop")
    sent = requests[0]
    assert sent["model"] == "test-model" and sent["max_tokens"] == 99
    assert sent["reasoning_effort"] == "none"


def test_reasoning_effort_can_be_turned_off(fake_server):
    base_url, requests = fake_server
    LLMClient(LLMSettings(base_url=base_url, reasoning_effort="")).chat(
        [{"role": "user", "content": "x"}]
    )
    assert "reasoning_effort" not in requests[0]


@pytest.mark.skipif(not os.environ.get("OWLGO_INTEGRATION"), reason="set OWLGO_INTEGRATION=1")
def test_real_ollama_answers():
    # Needs Ollama running with qwen3.5:9b pulled.
    reply = LLMClient().chat([{"role": "user", "content": "Reply with just the word: ready"}])
    assert reply.text and reply.finish_reason == "stop"
