"""Generic adapter: any agent CLI that reads a prompt on stdin and prints its answer.

Set AGENT_CMD to the command, e.g. AGENT_CMD="my-agent --non-interactive".
AGENT_CAN_EDIT=0 or 1 is passed in the environment. Configure your agent to honor it
(e.g. a read-only profile for 0), since this adapter can't enforce permissions itself.
"""

import os
import shlex
import subprocess
from pathlib import Path

from scripts.agents.base import AgentResult


class CommandAgent:
    name = "command"

    def __init__(self, command: str, timeout: int = 1800) -> None:
        self.argv = shlex.split(command)
        self.timeout = timeout

    def run(self, prompt: str, *, can_edit: bool, cwd: Path) -> AgentResult:
        env = {**os.environ, "AGENT_CAN_EDIT": "1" if can_edit else "0"}
        try:
            proc = subprocess.run(
                self.argv,
                input=prompt,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError:
            return AgentResult(127, f"`{self.argv[0]}` not found.")
        except subprocess.TimeoutExpired:
            return AgentResult(124, f"Agent timed out after {self.timeout}s.")
        output = proc.stdout if proc.returncode == 0 else f"{proc.stdout}\n{proc.stderr}".strip()
        return AgentResult(proc.returncode, output)
