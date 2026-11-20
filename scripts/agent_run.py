"""The orchestrator ("blueprint"). Vendor-agnostic: it only needs git, a gate command and an agent
adapter. CI files just call it, so the same logic runs on your laptop and in any CI system.

Usage:
    python -m scripts.agent_run code   --task task.md [--commit-message MSG]
    python -m scripts.agent_run fix    --log ci-failure.log
    python -m scripts.agent_run review --base origin/main --out review.md

Pick the agent with --agent or the AGENT env var: claude | command | fake.

Exit codes (the contract with whatever calls this):
    0  success
    1  gates still failing after the allowed rounds -> needs a human
    2  usage or configuration error
    3  fix already attempted on this branch -> needs a human
    4  the agent made no changes
    5  the agent itself failed to run (CLI missing, timeout, API error)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from scripts.agents import Agent, AgentResult, get_agent

EXIT_OK = 0
EXIT_GATES_FAILED = 1
EXIT_USAGE = 2
EXIT_CAP_REACHED = 3
EXIT_NO_CHANGES = 4
EXIT_AGENT_ERROR = 5

FIX_MARKER = "[agent-fix]"

CODE_PROMPT = """You are working in this repository. Implement the task below.

Rules:
- Follow AGENTS.md.
- Keep the change small and focused on the task. Add or update tests.
- Run `{gate_cmd}` and fix any failures before you finish.
- Do not commit, push or create branches. The pipeline does that.

Task:
{task}
"""

FIX_PROMPT = """`{gate_cmd}` fails after your change. Fix the cause.

Rules:
- Follow AGENTS.md.
- Do not skip, delete or weaken tests or checks to make them pass.
- Do not commit or push.

Last lines of the output:
{log}
"""

CI_FIX_PROMPT = """CI failed on this branch. Find and fix the cause.

Rules:
- Follow AGENTS.md.
- Do not skip, delete or weaken tests or checks to make them pass.
- Run `{gate_cmd}` before you finish. Do not commit or push.

Last lines of the CI log:
{log}
"""

REVIEW_PROMPT = """Review this change as a senior engineer on this codebase. Follow AGENTS.md.

Report only real problems: bugs, missing edge cases, security issues, missing tests, and
violations of AGENTS.md. Skip style nits that the linters already enforce.
Reply in short markdown: one bullet per issue with file and line, most severe first.
If there are no real problems, reply exactly: No blocking issues found.

Diff:
{diff}
"""


@dataclass
class Settings:
    gate_cmd: str = "make check"
    max_fix_rounds: int = 2
    gate_timeout: int = 900
    runs_dir: Path = field(default_factory=lambda: Path(".agent-runs"))
    log_tail_lines: int = 200
    max_diff_chars: int = 60_000

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            gate_cmd=os.getenv("GATE_CMD", "make check"),
            max_fix_rounds=int(os.getenv("MAX_FIX_ROUNDS", "2")),
            gate_timeout=int(os.getenv("GATE_TIMEOUT", "900")),
            runs_dir=Path(os.getenv("AGENT_RUNS_DIR", ".agent-runs")),
        )


def log(message: str) -> None:
    print(f"[agent-run] {message}", file=sys.stderr, flush=True)


def tail(text: str, lines: int) -> str:
    return "\n".join(text.splitlines()[-lines:])


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def has_changes(cwd: Path) -> bool:
    return bool(git(cwd, "status", "--porcelain").strip())


def commit_all(cwd: Path, message: str) -> None:
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", message)


def run_gates(settings: Settings, cwd: Path) -> tuple[bool, str]:
    """Deterministic step: no LLM. The exit code is the verdict."""
    try:
        proc = subprocess.run(
            settings.gate_cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=settings.gate_timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Gates timed out after {settings.gate_timeout}s."
    return proc.returncode == 0, proc.stdout + proc.stderr


class Recorder:
    """Saves every prompt and answer so a human can see what the agent did."""

    def __init__(self, runs_dir: Path, mode: str) -> None:
        self.dir = runs_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{mode}"
        self.count = 0

    def call(
        self, agent: Agent, prompt: str, *, can_edit: bool, cwd: Path, label: str
    ) -> AgentResult:
        self.count += 1
        log(f"agent '{agent.name}': {label}")
        result = agent.run(prompt, can_edit=can_edit, cwd=cwd)
        self.dir.mkdir(parents=True, exist_ok=True)
        record = {
            "label": label,
            "agent": agent.name,
            "can_edit": can_edit,
            "prompt": prompt,
            "exit_code": result.exit_code,
            "output": result.output,
        }
        path = self.dir / f"{self.count:02d}-{label}.json"
        path.write_text(json.dumps(record, indent=2))
        return result


def run_code(
    task: str, agent: Agent, settings: Settings, cwd: Path, commit_message: str | None = None
) -> int:
    """Implement -> gates -> fix (at most max_fix_rounds) -> commit."""
    rec = Recorder(settings.runs_dir, "code")
    prompt = CODE_PROMPT.format(task=task.strip(), gate_cmd=settings.gate_cmd)
    if rec.call(agent, prompt, can_edit=True, cwd=cwd, label="implement").exit_code != 0:
        return EXIT_AGENT_ERROR

    ok, output = run_gates(settings, cwd)
    rounds = 0
    while not ok and rounds < settings.max_fix_rounds:
        rounds += 1
        log(f"gates failed; fix round {rounds}/{settings.max_fix_rounds}")
        prompt = FIX_PROMPT.format(
            gate_cmd=settings.gate_cmd, log=tail(output, settings.log_tail_lines)
        )
        if rec.call(agent, prompt, can_edit=True, cwd=cwd, label=f"fix-{rounds}").exit_code:
            return EXIT_AGENT_ERROR
        ok, output = run_gates(settings, cwd)

    if not ok:
        log("gates still failing; handing over to a human")
        print(tail(output, settings.log_tail_lines))
        return EXIT_GATES_FAILED
    if not has_changes(cwd):
        log("gates pass but the agent made no changes")
        return EXIT_NO_CHANGES
    if commit_message:
        commit_all(cwd, commit_message)
        log(f"committed: {commit_message}")
    return EXIT_OK


def run_fix(ci_log: str, agent: Agent, settings: Settings, cwd: Path) -> int:
    """One fix attempt per branch. A second CI failure goes to a human."""
    if FIX_MARKER in git(cwd, "log", "-1", "--pretty=%B"):
        log("the last commit is already an agent fix; handing over to a human")
        return EXIT_CAP_REACHED

    rec = Recorder(settings.runs_dir, "fix")
    prompt = CI_FIX_PROMPT.format(
        gate_cmd=settings.gate_cmd, log=tail(ci_log, settings.log_tail_lines)
    )
    if rec.call(agent, prompt, can_edit=True, cwd=cwd, label="ci-fix").exit_code != 0:
        return EXIT_AGENT_ERROR

    ok, output = run_gates(settings, cwd)
    if not ok:
        print(tail(output, settings.log_tail_lines))
        return EXIT_GATES_FAILED
    if not has_changes(cwd):
        return EXIT_NO_CHANGES
    commit_all(cwd, f"Fix CI failure {FIX_MARKER}")
    log("committed the fix")
    return EXIT_OK


def run_review(base: str, out: Path, agent: Agent, settings: Settings, cwd: Path) -> int:
    """Read-only: writes the review to a file. Posting it is the CI layer's job."""
    diff = git(cwd, "diff", f"{base}...HEAD")
    if not diff.strip():
        out.write_text("No changes to review.\n")
        return EXIT_OK
    if len(diff) > settings.max_diff_chars:
        diff = diff[: settings.max_diff_chars] + "\n[diff truncated]"

    rec = Recorder(settings.runs_dir, "review")
    result = rec.call(
        agent, REVIEW_PROMPT.format(diff=diff), can_edit=False, cwd=cwd, label="review"
    )
    if result.exit_code != 0:
        return EXIT_AGENT_ERROR
    out.write_text(result.output.strip() + "\n")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--agent", default=os.getenv("AGENT", "claude"))
    sub = parser.add_subparsers(dest="mode", required=True)

    code = sub.add_parser("code", help="implement a task")
    code.add_argument("--task", type=Path, required=True, help="markdown file with the task")
    code.add_argument("--commit-message", help="commit when gates pass")

    fix = sub.add_parser("fix", help="fix a CI failure once")
    fix.add_argument("--log", type=Path, required=True, help="file with the failing CI log")

    review = sub.add_parser("review", help="review the diff against a base ref")
    review.add_argument("--base", default="origin/main")
    review.add_argument("--out", type=Path, default=Path("review.md"))

    args = parser.parse_args(argv)
    settings = Settings.from_env()
    cwd = Path.cwd()

    try:
        agent = get_agent(args.agent)
    except ValueError as error:
        log(str(error))
        return EXIT_USAGE

    if args.mode == "code":
        return run_code(args.task.read_text(), agent, settings, cwd, args.commit_message)
    if args.mode == "fix":
        return run_fix(args.log.read_text(), agent, settings, cwd)
    return run_review(args.base, args.out, agent, settings, cwd)


if __name__ == "__main__":
    sys.exit(main())
