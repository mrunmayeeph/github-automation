
from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import get_github_token, is_kill_switch_active, load_config
from core.github_client import GithubAPIError, GithubClient
from core.logger import get_logger
from core.state import load_state, save_state

logger = get_logger("daily_commit")

STATE_FILE = "daily_commit_state.json"


# Repository selection

def select_target_repo(
    repos: list[dict[str, Any]],
    last_repo: str | None,
) -> dict[str, Any]:
    """Choose a repository at random, avoiding *last_repo* when possible.

    Args:
        repos:     List of candidate repository dicts.
        last_repo: Name of the repository used in the previous run.

    Returns:
        The chosen repository dict.

    Raises:
        ValueError: if *repos* is empty.
    """
    if not repos:
        raise ValueError("No eligible repositories found.")

    candidates = [r for r in repos if r["name"] != last_repo]
    if not candidates:
        # Only one repo exists — we have no choice but to reuse it
        logger.warning(
            "Only one eligible repository available (%s); reusing it.", repos[0]["name"]
        )
        candidates = repos

    chosen = random.choice(candidates)
    logger.info("Selected repository: %s", chosen["name"])
    return chosen


# Idempotency guard

def already_ran_today(state: dict[str, Any]) -> bool:
    """Return True if the agent ran successfully today."""
    last_run = state.get("last_run_date")
    return last_run == str(date.today())


# Commit logic

def build_tracking_line(commit_index: int) -> str:
    """Return a single line to append to the tracking file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"[{ts}] automated commit #{commit_index}\n"


def commit_to_repo(
    client: GithubClient,
    owner: str,
    repo_name: str,
    tracking_file: str,
    commit_messages: list[str],
    num_commits: int,
    branch: str,
) -> int:
    """Write *num_commits* sequential updates to *tracking_file*.

    Each update appends a timestamped line and uses a distinct message
    drawn from *commit_messages* (cycled if the list is shorter than
    *num_commits*).

    Returns:
        The number of commits actually made.
    """
    commits_made = 0

    # Fetch the current file (may not exist yet)
    existing = client.get_file(owner, repo_name, tracking_file)
    if existing is None:
        current_content = ""
        current_sha: str | None = None
        logger.info("Tracking file '%s' not found — will create it.", tracking_file)
    else:
        import base64
        raw = existing.get("content", "")
        # GitHub wraps content in base64 with newlines
        current_content = base64.b64decode(raw.replace("\n", "")).decode("utf-8")
        current_sha = existing.get("sha")

    for i in range(1, num_commits + 1):
        message = commit_messages[(i - 1) % len(commit_messages)]
        new_line = build_tracking_line(commits_made + 1)
        new_content = current_content + new_line

        logger.info("Making commit %d/%d: '%s'", i, num_commits, message)
        client.create_or_update_file(
            owner=owner,
            repo=repo_name,
            file_path=tracking_file,
            content=new_content,
            commit_message=message,
            sha=current_sha,
            branch=branch,
        )
        # The next update needs the new SHA — fetch it
        updated = client.get_file(owner, repo_name, tracking_file)
        current_sha = updated["sha"] if updated else None
        current_content = new_content
        commits_made += 1

    return commits_made


# Main entry point

def run(force: bool = False) -> None:
    """Execute the Daily Commit Agent."""
    cfg = load_config()

    if is_kill_switch_active(cfg):
        logger.warning("Kill switch is active — exiting without making any API calls.")
        return

    state = load_state(STATE_FILE)

    if not force and already_ran_today(state):
        logger.info(
            "Agent already ran today (%s) against '%s'. Use --force to override.",
            state["last_run_date"],
            state.get("last_repo", "unknown"),
        )
        return

    token = get_github_token()
    client = GithubClient(token)

    # Resolve the authenticated username
    try:
        user = client.get_authenticated_user()
    except GithubAPIError as exc:
        logger.error("Failed to authenticate with GitHub: %s", exc)
        return

    username: str = user["login"]
    logger.info("Authenticated as: %s", username)

    # Fetch eligible repositories
    try:
        repos = client.list_user_repos(username)
    except GithubAPIError as exc:
        logger.error("Failed to list repositories: %s", exc)
        return

    if not repos:
        logger.error("No eligible repositories found for user '%s'.", username)
        return

    logger.info("Found %d eligible repositories.", len(repos))

    # Select target
    try:
        target = select_target_repo(repos, last_repo=state.get("last_repo"))
    except ValueError as exc:
        logger.error(str(exc))
        return

    # Resolve configuration values
    commit_cfg = cfg.get("daily_commit", {})
    tracking_file: str = commit_cfg.get("tracking_file", ".contributions")
    min_commits: int = commit_cfg.get("min_commits", 1)
    max_commits: int = commit_cfg.get("max_commits", 3)
    commit_messages: list[str] = commit_cfg.get(
        "commit_messages",
        ["chore: daily maintenance", "chore: update activity log", "chore: automated commit"],
    )
    num_commits = random.randint(min_commits, max_commits)
    logger.info("Will make %d commit(s) to '%s'.", num_commits, target["name"])

    # Determine the default branch
    try:
        branch = client.get_default_branch(username, target["name"])
    except GithubAPIError as exc:
        logger.warning("Could not determine default branch (%s); falling back to 'main'.", exc)
        branch = "main"

    # Perform commits
    try:
        made = commit_to_repo(
            client=client,
            owner=username,
            repo_name=target["name"],
            tracking_file=tracking_file,
            commit_messages=commit_messages,
            num_commits=num_commits,
            branch=branch,
        )
    except GithubAPIError as exc:
        logger.error("GitHub API error during commit phase: %s", exc)
        return
    except Exception as exc:
        logger.exception("Unexpected error during commit phase: %s", exc)
        return

    # Persist state
    new_state = {
        "last_run_date": str(date.today()),
        "last_repo": target["name"],
        "last_run_commits": made,
        "last_run_ts": datetime.now(timezone.utc).isoformat(),
    }
    save_state(STATE_FILE, new_state)
    logger.info(
        "Done. Made %d commit(s) to '%s'. State saved.",
        made,
        target["name"],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Daily Commit Agent — keeps your GitHub contribution graph active."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the once-per-day idempotency guard (useful for testing).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(force=args.force)