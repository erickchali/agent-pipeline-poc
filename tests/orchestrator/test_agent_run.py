"""Tests for the orchestrator's control flow: loops, limits and the exit-code contract.

They use a scripted fake agent and a throwaway git repo whose gate passes only when
status.txt says "pass", so no model or network is involved.
"""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts import agent_run
from scripts.agent_run import Settings
from scripts.agents import AgentResult, get_agent

Action = Callable[[Path], None]


class ScriptedAgent:
    name = "scripted"

    def __init__(self, actions: list[Action] | None = None, output: str = "done") -> None:
        self.actions = list(actions or [])
        self.output = output
        self.calls: list[tuple[str, bool]] = []

    def run(self, prompt: str, *, can_edit: bool, cwd: Path) -> AgentResult:
        self.calls.append((prompt, can_edit))
        if self.actions:
            self.actions.pop(0)(cwd)
        return AgentResult(0, self.output)


def write_status(value: str) -> Action:
    def action(cwd: Path) -> None:
        (cwd / "status.txt").write_text(value)

    return action


def do_nothing(_: Path) -> None:
    return None


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    (path / "gate.py").write_text(
        "import sys\nsys.exit(0 if open('status.txt').read().strip() == 'pass' else 1)\n"
    )
    (path / "status.txt").write_text("fail")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "initial")
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        gate_cmd=f'"{sys.executable}" gate.py',
        max_fix_rounds=2,
        runs_dir=tmp_path / "runs",
    )


def test_code_passes_first_try_and_commits(repo: Path, settings: Settings) -> None:
    agent = ScriptedAgent([write_status("pass")])

    code = agent_run.run_code("do it", agent, settings, repo, "Agent: do it")

    assert code == agent_run.EXIT_OK
    assert len(agent.calls) == 1
    assert git(repo, "log", "-1", "--pretty=%s").strip() == "Agent: do it"


def test_code_fixes_on_second_round(repo: Path, settings: Settings) -> None:
    agent = ScriptedAgent([write_status("still broken"), write_status("pass")])

    assert agent_run.run_code("do it", agent, settings, repo) == agent_run.EXIT_OK
    assert len(agent.calls) == 2
    assert "fails after your change" in agent.calls[1][0]


def test_code_stops_after_max_rounds(repo: Path, settings: Settings) -> None:
    agent = ScriptedAgent([write_status("broken")] * 10)

    assert agent_run.run_code("do it", agent, settings, repo) == agent_run.EXIT_GATES_FAILED
    assert len(agent.calls) == 1 + settings.max_fix_rounds


def test_code_reports_no_changes(repo: Path, settings: Settings) -> None:
    git(repo, "commit", "-q", "--allow-empty", "-m", "noop")
    (repo / "status.txt").write_text("pass")
    git(repo, "commit", "-q", "-am", "make gate pass")

    agent = ScriptedAgent([do_nothing])

    assert agent_run.run_code("do it", agent, settings, repo) == agent_run.EXIT_NO_CHANGES


def test_fix_commits_with_marker(repo: Path, settings: Settings) -> None:
    agent = ScriptedAgent([write_status("pass")])

    assert agent_run.run_fix("CI log", agent, settings, repo) == agent_run.EXIT_OK
    assert agent_run.FIX_MARKER in git(repo, "log", "-1", "--pretty=%s")


def test_fix_hands_over_after_one_attempt(repo: Path, settings: Settings) -> None:
    git(repo, "commit", "-q", "--allow-empty", "-m", f"Fix CI failure {agent_run.FIX_MARKER}")
    agent = ScriptedAgent([write_status("pass")])

    assert agent_run.run_fix("CI log", agent, settings, repo) == agent_run.EXIT_CAP_REACHED
    assert agent.calls == []


def test_review_is_read_only_and_writes_output(
    repo: Path, settings: Settings, tmp_path: Path
) -> None:
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "new.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "feature")
    out = tmp_path / "review.md"
    agent = ScriptedAgent(output="No blocking issues found.")

    assert agent_run.run_review("main", out, agent, settings, repo) == agent_run.EXIT_OK
    assert agent.calls[0][1] is False
    assert "new.py" in agent.calls[0][0]
    assert out.read_text().strip() == "No blocking issues found."


def test_every_agent_call_is_recorded(repo: Path, settings: Settings) -> None:
    agent = ScriptedAgent([write_status("broken"), write_status("pass")])

    agent_run.run_code("do it", agent, settings, repo)

    records = sorted(settings.runs_dir.glob("*/*.json"))
    assert [path.name for path in records] == ["01-implement.json", "02-fix-1.json"]


def test_unknown_agent_is_a_usage_error() -> None:
    with pytest.raises(ValueError):
        get_agent("does-not-exist")
