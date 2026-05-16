# GitHub Activity Bot

An automated, configurable system that keeps your GitHub contribution graph active.
Two independent agents run on a schedule: one makes small daily commits to existing repositories,
and the other periodically generates and pushes brand-new stub projects to your account.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Prerequisites](#2-prerequisites)
3. [Setup Instructions](#3-setup-instructions)
4. [Configuration Guide](#4-configuration-guide)
5. [API Key Setup](#5-api-key-setup)
6. [Running the Agents](#6-running-the-agents)
7. [Scheduling](#7-scheduling)
8. [Kill Switch](#8-kill-switch)
9. [Idempotency](#9-idempotency)
10. [Logging](#10-logging)
11. [State Persistence](#11-state-persistence)
12. [GitHub API Rate Limits](#12-github-api-rate-limits)
13. [Troubleshooting](#13-troubleshooting)
14. [Project Structure](#14-project-structure)

---

## 1. Project Overview

**GitHub Activity Bot** is a Python automation tool with two agents:

- **Daily Commit Agent** — selects a random non-forked, non-archived repository you own and
  makes 1–3 small commits per day to a tracking file (`.contributions` by default), keeping
  your contribution graph green.
- **Project Creator Agent** — periodically creates a brand-new public stub repository with a
  README, `.gitignore`, and a starter source file in the language of your choice. It can
  optionally call the HuggingFace Inference API for AI-generated project ideas, and gracefully
  falls back to a built-in pool when the API is unavailable.

Both agents are fully configurable via `config.yaml`, persist their state between runs in JSON
files, and log structured timestamped output to stdout and rotating log files.

---

## 2. Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10 or higher |
| pip | bundled with Python |
| Git | any recent version (only needed if you clone via HTTPS/SSH) |
| A GitHub account | — |
| A GitHub Personal Access Token | `repo` scope — see §5 |

> **No OS-level dependencies** beyond a standard Python installation are required.
> The project is tested on Linux, macOS, and Windows (PowerShell / WSL).

---

## 3. Setup Instructions

### 3.1 Clone the Repository

```bash
git clone https://github.com/<your-username>/github-activity-bot.git
cd github-activity-bot
```

### 3.2 Create a Virtual Environment

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3.3 Install Dependencies

```bash
pip install -r requirements.txt
```

### 3.4 Configure Secrets

```bash
cp .env.example .env
# Open .env in your editor and fill in GITHUB_TOKEN (see §5)
```

### 3.5 (Optional) Adjust Configuration

Open `config.yaml` and edit any values to suit your preferences (see §4).

---

## 4. Configuration Guide

All configuration lives in **`config.yaml`**. No magic numbers appear in the source code.

```yaml
kill_switch: false
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `kill_switch` | bool | `false` | Set to `true` to immediately halt both agents without making any API calls. |

---

### `daily_commit` section

```yaml
daily_commit:
  tracking_file: ".contributions"
  min_commits: 1
  max_commits: 3
  commit_messages:
    - "chore: daily maintenance update"
    - ...
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `tracking_file` | string | `.contributions` | Path of the file that is created/updated in the target repo. Can be any valid file path (e.g. `logs/activity.log`). |
| `min_commits` | int | `1` | Minimum number of commits made per run. |
| `max_commits` | int | `3` | Maximum number of commits made per run (inclusive). Must be ≥ `min_commits`. |
| `commit_messages` | list[str] | *(see config.yaml)* | Pool of commit messages. Messages are cycled when fewer entries exist than `max_commits`. Add as many as you like. |

---

### `project_creator` section

```yaml
project_creator:
  interval_days: 7
  languages:
    - python
    - javascript
  private_repos: false
  ai_api:
    enabled: false
    endpoint: "https://api-inference.huggingface.co/models/..."
    timeout_seconds: 15
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `interval_days` | int | `7` | Minimum number of days between project creations. |
| `languages` | list[str] | `[python, javascript]` | Languages available for new projects. Currently supported values: `python`, `javascript`. |
| `private_repos` | bool | `false` | Set to `true` to create new repositories as private. |
| `ai_api.enabled` | bool | `false` | Enable AI-powered project idea generation via HuggingFace. |
| `ai_api.endpoint` | string | *(HuggingFace Mistral URL)* | HuggingFace Inference API URL. Replace with any compatible model endpoint. |
| `ai_api.timeout_seconds` | int | `15` | HTTP timeout for AI API requests. Falls back to built-in ideas on timeout. |

---

## 5. API Key Setup

### GitHub Personal Access Token (PAT)

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**.
2. Click **"Generate new token (classic)"**.
3. Set an expiry (90 days recommended).
4. Select the **`repo`** scope (full repository read/write access).
5. Click **"Generate token"** and copy it immediately — GitHub will not show it again.
6. Paste it into your `.env` file:

```dotenv
GITHUB_TOKEN=ghp_YourTokenHere
```


### HuggingFace Token (optional)

Only required when `project_creator.ai_api.enabled: true`.

1. Create a free account at <https://huggingface.co>.
2. Go to **Profile → Settings → Access Tokens**.
3. Click **"New token"**, choose the **Read** role.
4. Copy the token and add it to `.env`:

```dotenv
HUGGINGFACE_API_TOKEN=hf_YourTokenHere
```

---

## 6. Running the Agents

All commands assume your virtual environment is activated and you are in the project root.

### Daily Commit Agent

```bash
# Normal run (no-op if already ran today)
python agents/daily_commit.py

# Force a run regardless of today's guard
python agents/daily_commit.py --force
```

### Project Creator Agent

```bash
# Normal run (no-op if not yet due based on interval_days)
python agents/project_creator.py

# Force a run regardless of the scheduling interval
python agents/project_creator.py --force
```

### Running Tests

```bash
pytest
```

---

## 7. Scheduling

Pick **one** of the following methods.

### Option A — cron (Linux / macOS)

```bash
crontab -e
```

Add these lines (adjust paths to your actual install location):

```cron
# Daily Commit Agent — runs every day at 09:00
0 9 * * * /path/to/.venv/bin/python /path/to/github-activity-bot/agents/daily_commit.py >> /path/to/github-activity-bot/logs/cron.log 2>&1

# Project Creator Agent — runs every day at 10:00 (interval enforced in code)
0 10 * * * /path/to/.venv/bin/python /path/to/github-activity-bot/agents/project_creator.py >> /path/to/github-activity-bot/logs/cron.log 2>&1
```

### Option B — Windows Task Scheduler

1. Open **Task Scheduler → Create Basic Task**.
2. Set the trigger to **Daily** at your preferred time.
3. Set the action to **Start a program**:
   - Program: `C:\path\to\.venv\Scripts\python.exe`
   - Arguments: `C:\path\to\github-activity-bot\agents\daily_commit.py`
4. Repeat for `project_creator.py`.

### Option C — GitHub Actions (run in the cloud)

Create `.github/workflows/bot.yml` in your repo:

```yaml
name: GitHub Activity Bot

on:
  schedule:
    - cron: "0 9 * * *"   # daily at 09:00 UTC
  workflow_dispatch:       # allow manual runs

jobs:
  daily-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python agents/daily_commit.py
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  project-creator:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python agents/project_creator.py
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

> Add your PAT as a repository secret named `GITHUB_TOKEN` under
> **Settings → Secrets and variables → Actions**.
>
> ⚠️ **State caveat**: GitHub Actions runners are ephemeral. To preserve state between runs,
> commit the `state/` directory back to the repository at the end of each workflow, or use a
> persistent external store (e.g. an S3 bucket or a Gist).

---

## 8. Kill Switch

To pause both agents immediately **without modifying or deleting any files**:

1. Open `config.yaml`.
2. Set the top-level key:
   ```yaml
   kill_switch: true
   ```
3. Save the file.

Both agents check this flag before making any API calls. They will log a warning and exit cleanly.

To resume, set it back to `false`.

---

## 9. Idempotency

Both agents are designed to be safe to run multiple times — re-running them produces no
additional side effects once they have already acted for the current period.

**Daily Commit Agent** — on each run, the agent reads `state/daily_commit_state.json` and
compares `last_run_date` against today's date. If they match, the agent logs a message and
exits immediately without making any API calls. Use `--force` to override this guard during
testing.

**Project Creator Agent** — on each run, the agent checks how many days have elapsed since
`last_run_date`. If fewer days have passed than `interval_days` (default: 7), the agent exits
without creating anything. The list of already-created project names is also persisted, so the
same project name is never pushed twice.

Deleting a state file resets that agent as if it had never run.

---

## 10. Logging

All log output is **structured** with a consistent format:

```
YYYY-MM-DDTHH:MM:SS | LEVEL    | logger_name | message
```

Example:
```
2024-03-15T09:00:01 | INFO     | daily_commit | Authenticated as: octocat
2024-03-15T09:00:02 | INFO     | daily_commit | Selected repository: my-project
2024-03-15T09:00:03 | INFO     | daily_commit | Making commit 1/2: 'chore: daily maintenance update'
2024-03-15T09:00:05 | INFO     | daily_commit | Done. Made 2 commit(s) to 'my-project'. State saved.
```

Each agent writes to **two destinations simultaneously**:

| Destination | Location | Behaviour |
|-------------|----------|-----------|
| stdout | terminal | all severities |
| log file | `logs/daily_commit.log` / `logs/project_creator.log` | rotating, 5 MB × 3 backups |

Severity levels used: `DEBUG` (internal detail), `INFO` (normal progress), `WARNING` (recoverable issues, e.g. AI API unavailable), `ERROR` (action failed, agent exits gracefully).

Log files and the `logs/` directory are excluded from version control via `.gitignore`.

---

## 11. State Persistence

**Why JSON files?**

JSON was chosen over SQLite or a database for three reasons:

1. **Write frequency is negligible** — each agent writes state at most once per day. There is no concurrent access, no transaction requirement, and no query complexity that would justify a database.
2. **Human-readable** — the state files can be inspected and manually corrected with any text editor, without needing database tooling.
3. **Zero extra dependencies** — `json` is part of the Python standard library. Adding SQLite or another store would increase the dependency surface for no practical gain at this scale.

State is stored in `state/` (git-ignored):

| File | Key fields |
|------|-----------|
| `daily_commit_state.json` | `last_run_date`, `last_repo`, `last_run_commits`, `last_run_ts` |
| `project_creator_state.json` | `last_run_date`, `created_projects` (list), `last_project`, `last_repo_url` |

Deleting a state file resets the corresponding agent as if it had never run.

---

## 12. GitHub API Rate Limits

GitHub allows **5,000 authenticated API requests per hour** for personal access tokens.

This bot is extremely conservative with API calls. A typical daily commit run makes **4–8
requests** (authenticate, list repos, get file, 1–3 file updates). A project creation run
makes roughly **8–12 requests** (authenticate, list repos, create repo, seed 4 files).

There is no polling, no pagination beyond what is necessary, and no redundant calls. The
`GithubClient` class makes one retry on 5xx errors before raising — it never hammers the API
in a loop.

You would need to run the agents hundreds of times per hour to approach the rate limit, which
the idempotency guards make impossible under normal operation.

---

## 13. Troubleshooting

### Error: `GITHUB_TOKEN is not set`

**Cause**: The `.env` file is missing, or `GITHUB_TOKEN` was not exported in the shell.

**Fix**:
1. Confirm `.env` exists in the project root: `ls -la .env`
2. Confirm it contains `GITHUB_TOKEN=ghp_...`
3. If running via cron, ensure the full path to the Python executable (inside the venv) is used,
   and that the `GITHUB_TOKEN` environment variable is set in the crontab environment or passed
   explicitly.

---

### Error: `GitHub API error 401: Bad credentials`

**Cause**: The token in `.env` is invalid, expired, or does not have the `repo` scope.

**Fix**:
1. Generate a new token (see §5).
2. Replace the value in `.env`.
3. Verify the token has the `repo` scope enabled.

---

### Error: `GitHub API error 422: Repository creation failed — name already exists`

**Cause**: The Project Creator tried to create a repository whose name already exists on your
account. This can happen if the state file was deleted or corrupted.

**Fix**: The agent automatically appends a numeric suffix (e.g. `url-shortener-2`) to deduplicate.
If you see this repeatedly, check that `state/project_creator_state.json` is being persisted
between runs (see §7 GitHub Actions caveat).

---

### Error: `No eligible repositories found`

**Cause**: Your account has no non-forked, non-archived repositories, **or** all your repos are
forks/archives.

**Fix**:
1. Create at least one original (non-fork) repository on GitHub.
2. If you own repos that were auto-archived, unarchive them in GitHub Settings.

---


### Some or all files missing after project creation (README, .gitignore, source file)

**Cause**: The previous version used `auto_init=True` when creating the repo, which let GitHub
seed its own `README.md`. When our code then tried to overwrite it, the SHA had already changed,
causing a conflict that silently aborted the file seeding.

**Fix**: Update to the latest `project_creator.py` and `project_templates.py`. The agent now
uses `auto_init=False` and owns every file from scratch. It also retries each file up to 3 times
with back-off, and distinguishes between required files (`README.md`, `.gitignore`, source file)
and optional ones (`requirements.txt` / `package.json`) so a failure on an optional file never
blocks the required ones. After a run, check `state/project_creator_state.json` for
`"last_seed_ok": true` to confirm all required files were pushed successfully.

### Commits appear but the contribution graph is not updating

**Cause**: GitHub contribution graphs only count commits to the **default branch** (usually
`main` or `master`) of non-fork repositories. The bot always targets the default branch, so
this is usually a visibility delay.

**Fix**: Wait up to 24 hours. If the graph still does not update, verify that the target
repository is not a fork (`fork: false` in the API response).

---

### `ModuleNotFoundError: No module named 'yaml'` (or similar)

**Cause**: Dependencies are not installed, or the virtual environment is not activated.

**Fix**:
```bash
source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
```

---

## 14. Project Structure

```
github-activity-bot/
│
├── agents/                     # Agent entry points
│   ├── __init__.py
│   ├── daily_commit.py         # Daily Commit Agent — main logic
│   ├── project_creator.py      # Project Creator Agent — main logic
│   └── project_templates.py    # Built-in project ideas and file templates
│
├── core/                       # Shared reusable modules
│   ├── __init__.py
│   ├── config.py               # YAML config loader + env var helpers
│   ├── github_client.py        # GitHub REST API v3 client
│   ├── logger.py               # Structured logging (stdout + rotating file)
│   └── state.py                # JSON-backed state persistence
│
├── tests/                      # Pytest test suite
│   ├── __init__.py
│   ├── test_core.py            # Tests for config, state, logging
│   ├── test_daily_commit.py    # Idempotency + repo selection tests
│   └── test_project_creator.py # Scheduling + idea generation tests
│
├── state/                      # Runtime state (git-ignored)
│   ├── daily_commit_state.json     # Created on first run
│   └── project_creator_state.json  # Created on first run
│
├── logs/                       # Rotating log files (git-ignored)
│   ├── daily_commit.log
│   └── project_creator.log
│
├── .env                        # Secrets — NEVER commit (git-ignored)
├── .env.example                # Template for .env
├── .gitignore                  # Excludes .env, logs/, state/, venv/
├── config.yaml                 # All configurable parameters
├── pytest.ini                  # Pytest configuration
├── requirements.txt            # Pinned Python dependencies
└── README.md                   # This file
```

---

## State Files

State is persisted in `state/` as human-readable JSON:

| File | Contents |
|------|----------|
| `daily_commit_state.json` | `last_run_date`, `last_repo`, `last_run_commits`, `last_run_ts` |
| `project_creator_state.json` | `last_run_date`, `created_projects` (list), `last_project`, `last_repo_url` |

Deleting a state file resets the corresponding agent as if it had never run.

---

## License

MIT — see [LICENSE](LICENSE) for details.
