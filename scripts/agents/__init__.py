"""Agent registry. To add a vendor, write one adapter class and register it here."""

import os

from scripts.agents.base import Agent, AgentResult
from scripts.agents.claude_code import ClaudeCodeAgent
from scripts.agents.command import CommandAgent
from scripts.agents.fake import FakeAgent

__all__ = ["Agent", "AgentResult", "get_agent"]

AGENTS = ("claude", "command", "fake")


def get_agent(name: str) -> Agent:
    timeout = int(os.getenv("AGENT_TIMEOUT", "1800"))
    if name == "claude":
        return ClaudeCodeAgent(max_turns=int(os.getenv("AGENT_MAX_TURNS", "60")), timeout=timeout)
    if name == "command":
        command = os.getenv("AGENT_CMD")
        if not command:
            raise ValueError("The 'command' agent needs AGENT_CMD set to your agent's CLI command.")
        return CommandAgent(command, timeout=timeout)
    if name == "fake":
        return FakeAgent()
    raise ValueError(f"Unknown agent {name!r}. Options: {', '.join(AGENTS)}")
