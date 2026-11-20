# agent-pipeline-poc

A small, vendor-agnostic proof of concept for automated **code → review → fix → CI → CD** with coding agents.

The app (a tiny FastAPI notes API) is only there so the agents have real code to work on. The point is the pipeline around it.

## The six blocks, and where they live

| Block | What it does | Here | To swap it |
| --- | --- | --- | --- |
| **Trigger** | Starts a run with a task | Issue label `agent`, PR events, CI failure (`.github/workflows/agent-*.yml`) | Call the same orchestrator commands from another CI or a chat bot |
| **Sandbox** | Isolated place to run | GitHub runner (CI), `docker-compose.yml` + `Dockerfile.sandbox` (local) | Any container, VM or CI runner |
| **Harness** | The agent loop | `scripts/agents/` adapters: `claude`, `command` (any CLI), `fake` | Write one adapter class, register it in `scripts/agents/__init__.py` |
| **Gates** | Pass/fail verdict | `make check` (ruff, mypy strict, pytest) | Set `GATE_CMD` |
| **Orchestrator** | Loops, limits, commits | `scripts/agent_run.py` | Nothing: it's plain Python + git |
| **Delivery** | Human review, then CD | Branch protection + `.github/workflows/cd.yml` (simulated) | Replace the `docker run` steps with your deploy |

The CI files are thin on purpose: they handle GitHub-specific input and output (tokens, pushes, comments) and call the orchestrator for everything else. The same commands run on your laptop.

## Run it locally

```bash
make install
make check                       # the gate: lint, types, tests

# Dry-run the orchestrator with the fake agent (no model, no key). Exits 4: "no changes".
python -m scripts.agent_run --agent fake code --task docs/starter-issues/01-delete-note.md

# Real run with Claude Code through OpenRouter (needs the `claude` CLI)
export ANTHROPIC_BASE_URL=https://openrouter.ai/api
export ANTHROPIC_AUTH_TOKEN="<your OpenRouter key>"
export ANTHROPIC_API_KEY=""      # must be empty
git checkout -b agent/try-delete
python -m scripts.agent_run --agent claude code \
  --task docs/starter-issues/01-delete-note.md --commit-message "Agent: delete endpoint"

# Review the current branch against main
python -m scripts.agent_run --agent claude review --base main --out review.md
```

Or inside the sandbox container (it reads `OPENROUTER_API_KEY` from your shell):

```bash
docker compose run --rm sandbox python -m scripts.agent_run code --task docs/starter-issues/01-delete-note.md
```

Every prompt and answer is saved under `.agent-runs/` (uploaded as a CI artifact too).

## Orchestrator modes and exit codes

| Mode | Flow |
| --- | --- |
| `code --task FILE` | implement → `make check` → fix (max `MAX_FIX_ROUNDS`, default 2) → commit |
| `fix --log FILE` | one fix per branch → `make check` → commit marked `[agent-fix]`. A second CI failure goes to a human |
| `review --base REF` | read-only review of the diff, written to a file |

| Exit code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Gates still fail after the allowed rounds: needs a human |
| 2 | Usage or configuration error |
| 3 | A fix was already tried on this branch: needs a human |
| 4 | The agent made no changes |
| 5 | The agent failed to run (CLI missing, timeout, API error) |

Settings come from env vars: `AGENT`, `GATE_CMD`, `MAX_FIX_ROUNDS`, `GATE_TIMEOUT`, `AGENT_TIMEOUT`, `AGENT_MAX_TURNS`, `AGENT_CMD` (for the `command` adapter).

## Set up the GitHub side

1. **A GitHub App for the agent.** Pushes made with the default `GITHUB_TOKEN` don't trigger CI, so the agent pushes as an app.
   - Settings → Developer settings → GitHub Apps → New GitHub App. Any name and homepage URL; turn the webhook off.
   - Repository permissions: **Contents**, **Issues**, **Pull requests**: read and write.
   - Create it, generate a private key, then install it on this repo only.
   - In this repo's Settings → Secrets and variables → Actions: add variable `AGENT_APP_ID` and secret `AGENT_APP_PRIVATE_KEY` (the whole `.pem` file).
2. **The model key.** Add secret `OPENROUTER_API_KEY`. The agent workflows route Claude Code through OpenRouter by setting `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` and an empty `ANTHROPIC_API_KEY` in their `env:` blocks. To go direct to Anthropic instead, replace those three lines with `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}`. To try the plumbing without any key, add variable `AGENT` = `fake`.
3. **A label** named `agent`.
4. **Branch protection on `main`:** require a pull request with 1 approval and the `check` status from CI. Agents never merge.
5. **Optional manual gate for CD:** Settings → Environments → `production` → required reviewers.

## Try it

1. Open an issue with the text of a file from `docs/starter-issues/`.
2. Add the `agent` label. The **Agent task** workflow implements it and opens a PR, or comments on the issue explaining why it stopped.
3. **CI** runs on the PR. If it fails, **Agent fix** tries once.
4. **Agent review** comments on the PR.
5. You review and merge. **CD** builds the image, deploys to staging, then runs a production canary with automatic rollback.

## Safety limits built in

- Agents only run on events from collaborators (labels need triage access; reviews skip fork PRs).
- Agent jobs get test settings and the model key only, no production secrets.
- Review mode is read-only, enforced by the adapter's tool permissions.
- Every loop is capped: agent turns and timeout, fix rounds, one CI fix per branch, job timeouts.
- Agents never merge or deploy. Releases are decided by fixed health checks.
