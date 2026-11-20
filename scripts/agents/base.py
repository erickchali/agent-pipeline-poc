"""The harness contract. Every coding agent is wrapped to look like this, so the orchestrator never
depends on a specific vendor."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AgentResult:
    exit_code: int
    output: str


class Agent(Protocol):
    name: str

    def run(self, prompt: str, *, can_edit: bool, cwd: Path) -> AgentResult:
        """Run one non-interactive agent session.

        can_edit=False means read-only (review). The adapter must enforce it with the
        agent's own permission settings, not just by asking nicely in the prompt.
        """
        ...
