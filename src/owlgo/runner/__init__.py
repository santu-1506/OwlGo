"""Run code against problem tests and report what happened on each test."""

from owlgo.runner.local import LocalRunner
from owlgo.runner.results import RunResult, TestResult

__all__ = ["LocalRunner", "RunResult", "TestResult"]
