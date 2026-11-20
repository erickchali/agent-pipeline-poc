"""Adapter for Claude Code's non-interactive mode (`claude -p`)."""

import contextlib
import json
import subprocess
from pathlib import Path

from scripts.agents.base import AgentResult

EDIT_TOOLS = "Read,Edit,Write,Glob,Grep,Bash(make check),Bash(make test),Bash(pytest:*)"
READ_TOOLS = "Read,Glob,Grep"


class ClaudeCodeAgent:
    name = "claude"

    def __init__(self, max_turns: int = 60, timeout: int = 1800, binary: str = "claude") -> None:
        self.max_turns = max_turns
        self.timeout = timeout
        self.binary = binary

    def run(self, prompt: str, *, can_edit: bool, cwd: Path) -> AgentResult:
        cmd = [
            self.binary,
            "-p",
            prompt,
            "--allowedTools",
            EDIT_TOOLS if can_edit else READ_TOOLS,
            "--max-turns",
            str(self.max_turns),
            "--output-format",
            "json",
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, timeout=self.timeout
            )
        except FileNotFoundError:
            return AgentResult(127, f"`{self.binary}` not found. Install the Claude Code CLI.")
        except subprocess.TimeoutExpired:
            return AgentResult(124, f"Agent timed out after {self.timeout}s.")

        output, exit_code = proc.stdout, proc.returncode
        with contextlib.suppress(json.JSONDecodeError, AttributeError):
            data = json.loads(proc.stdout)
            output = str(data.get("result", proc.stdout))
            if data.get("is_error") and exit_code == 0:
                exit_code = 1
        if exit_code != 0:
            output = f"{output}\n{proc.stderr}".strip()
        return AgentResult(exit_code, output)
