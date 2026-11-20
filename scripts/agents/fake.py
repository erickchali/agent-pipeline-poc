"""A stand-in agent that changes nothing. Dry-runs the whole pipeline with no model or API key."""

from pathlib import Path

from scripts.agents.base import AgentResult


class FakeAgent:
    name = "fake"

    def run(self, prompt: str, *, can_edit: bool, cwd: Path) -> AgentResult:
        if can_edit:
            return AgentResult(0, "Fake agent: made no changes.")
        return AgentResult(0, "Fake review: no blocking issues found.")
