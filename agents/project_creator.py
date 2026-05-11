
from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.project_templates import (
    BUILTIN_IDEAS,
    render_deps_file,
    render_gitignore,
    render_readme,
    render_source,
)
from core.config import get_github_token, is_kill_switch_active, load_config
from core.github_client import GithubAPIError, GithubClient
from core.logger import get_logger
from core.state import load_state, save_state

logger = get_logger("project_creator")

STATE_FILE = "project_creator_state.json"

# Required files — seeding is only considered successful when ALL of these exist.
REQUIRED_FILES = {"README.md", ".gitignore"}  # source file added dynamically per language

# Scheduling guard

def is_due(state: dict[str, Any], interval_days: int) -> bool:
    """Return True if enough days have passed since the last run."""
    last_run = state.get("last_run_date")
    if not last_run:
        return True
    try:
        last_date = date.fromisoformat(last_run)
    except ValueError:
        return True
    return (date.today() - last_date).days >= interval_days


# Idea generation

def fetch_ai_idea(ai_cfg: dict[str, Any]) -> dict[str, str] | None:
    """Attempt to generate a project idea via the HuggingFace Inference API.

    Returns a dict with keys ``name`` and ``description`` on success,
    or None if the API is unavailable / misconfigured.
    """
    import os

    try:
        import requests as req
    except ImportError:
        return None

    api_url = ai_cfg.get("endpoint", "")
    api_key = os.getenv("HUGGINGFACE_API_TOKEN", "").strip()

    if not api_url or not api_key:
        logger.debug("AI API not configured — skipping.")
        return None

    prompt = (
        "Generate a short software project idea suitable for a beginner programmer. "
        "Reply with ONLY a JSON object with two keys: "
        "\"name\" (a hyphenated slug, max 40 chars) and "
        "\"description\" (one sentence, max 120 chars). "
        "No extra text."
    )

    try:
        timeout = ai_cfg.get("timeout_seconds", 15)
        response = req.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"inputs": prompt, "parameters": {"max_new_tokens": 80}},
            timeout=timeout,
        )
        response.raise_for_status()
        raw = response.json()

        if isinstance(raw, list) and raw:
            text = raw[0].get("generated_text", "")
        else:
            text = str(raw)

        import json, re
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            idea = json.loads(match.group())
            name = idea.get("name", "").strip().lower().replace(" ", "-")
            desc = idea.get("description", "").strip()
            if name and desc:
                logger.info("AI-generated idea: %s — %s", name, desc)
                return {"name": name, "description": desc}

    except Exception as exc:
        logger.warning("AI API unavailable (%s) — falling back to built-in ideas.", exc)

    return None


def pick_builtin_idea(used_names: set[str]) -> dict[str, str] | None:
    """Return a random unused idea from BUILTIN_IDEAS."""
    available = [i for i in BUILTIN_IDEAS if i["name"] not in used_names]
    if not available:
        logger.warning("All built-in ideas have been used.")
        return None
    return random.choice(available)


def generate_project_idea(
    cfg: dict[str, Any], used_names: set[str]
) -> dict[str, str] | None:
    """Return a project idea dict with 'name' and 'description'."""
    ai_cfg = cfg.get("project_creator", {}).get("ai_api", {})
    if ai_cfg.get("enabled", False):
        idea = fetch_ai_idea(ai_cfg)
        if idea and idea["name"] not in used_names:
            return idea
        if idea:
            logger.info(
                "AI-generated name '%s' already used — falling back.", idea["name"]
            )

    return pick_builtin_idea(used_names)


# Repository name deduplication

def make_unique_name(base_name: str, existing_repo_names: set[str]) -> str:
    """Append a numeric suffix to *base_name* until it is unique."""
    if base_name not in existing_repo_names:
        return base_name
    for i in range(2, 100):
        candidate = f"{base_name}-{i}"
        if candidate not in existing_repo_names:
            return candidate
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{base_name}-{suffix}"


# File seeding

def _upload_file(
    client: GithubClient,
    owner: str,
    repo_name: str,
    filename: str,
    content: str,
    branch: str,
    retries: int = 3,
) -> bool:
    """Upload a single file to the repository, retrying on transient failures.

    Returns True on success, False if all attempts fail.
    """
    for attempt in range(1, retries + 1):
        try:
            existing = client.get_file(owner, repo_name, filename)
            sha = existing["sha"] if existing else None
            client.create_or_update_file(
                owner=owner,
                repo=repo_name,
                file_path=filename,
                content=content,
                commit_message=f"chore: add {filename}",
                sha=sha,
                branch=branch,
            )
            logger.info("Seeded file: %s", filename)
            return True
        except GithubAPIError as exc:
            logger.warning(
                "Attempt %d/%d failed for '%s': %s", attempt, retries, filename, exc
            )
            if attempt < retries:
                time.sleep(2 * attempt)  # back-off: 2s, 4s
    logger.error("Failed to seed '%s' after %d attempts.", filename, retries)
    return False


def seed_repository(
    client: GithubClient,
    owner: str,
    repo_name: str,
    project_name: str,
    description: str,
    language: str,
    branch: str,
) -> tuple[bool, list[str]]:
    """Push all required and optional files to the new repository.

    Files are uploaded sequentially with a short pause between each to avoid
    409 conflicts on rapid successive writes to a fresh repo.

    The minimum required set is: README.md, .gitignore, and the language
    source file. The deps file is a bonus; its failure does not fail the run.

    Returns:
        (all_required_ok, list_of_failed_filenames)
    """
    lang = language.lower()
    src_filename = "main.py" if lang == "python" else "index.js"
    deps_filename, deps_content = render_deps_file(project_name, description, lang)

    # Required files — run must guarantee all of these are present
    required: list[tuple[str, str]] = [
        ("README.md",   render_readme(project_name, description, lang)),
        (".gitignore",  render_gitignore(lang)),
        (src_filename,  render_source(project_name, description, lang)),
    ]

    # Optional extras — nice to have but not blocking
    optional: list[tuple[str, str]] = [
        (deps_filename, deps_content),
    ]

    failed: list[str] = []

    for filename, content in required:
        ok = _upload_file(client, owner, repo_name, filename, content, branch)
        if not ok:
            failed.append(filename)
        time.sleep(1)  # give GitHub a moment between commits

    for filename, content in optional:
        ok = _upload_file(client, owner, repo_name, filename, content, branch)
        if not ok:
            logger.warning("Optional file '%s' could not be seeded — skipping.", filename)
        time.sleep(1)

    all_required_ok = len(failed) == 0
    return all_required_ok, failed


# Branch initialisation

def initialise_branch(
    client: GithubClient,
    owner: str,
    repo_name: str,
    branch: str,
    project_name: str,
    description: str,
    language: str,
) -> bool:
    """Create the very first commit on an empty repo using README.md as the seed.

    When auto_init=False the repo has no commits and no branch yet.
    The Contents API requires at least one existing commit to push to a branch.
    We bootstrap by pushing README.md first (sha=None = create), which
    simultaneously creates the branch and its first commit.

    Returns True on success.
    """
    lang = language.lower()
    readme_content = render_readme(project_name, description, lang)
    try:
        client.create_or_update_file(
            owner=owner,
            repo=repo_name,
            file_path="README.md",
            content=readme_content,
            commit_message="chore: initial commit",
            sha=None,
            branch=branch,
        )
        logger.info("Branch '%s' initialised with README.md.", branch)
        return True
    except GithubAPIError as exc:
        logger.error("Failed to initialise branch '%s': %s", branch, exc)
        return False


# Main entry point

def run(force: bool = False) -> None:
    """Execute the Project Creator Agent."""
    cfg = load_config()

    if is_kill_switch_active(cfg):
        logger.warning("Kill switch is active — exiting without making any API calls.")
        return

    creator_cfg = cfg.get("project_creator", {})
    interval_days: int = creator_cfg.get("interval_days", 7)
    language_pool: list[str] = creator_cfg.get("languages", ["python", "javascript"])
    private_repos: bool = creator_cfg.get("private_repos", False)

    state = load_state(STATE_FILE)
    created_projects: list[str] = state.get("created_projects", [])
    used_names: set[str] = set(created_projects)

    if not force and not is_due(state, interval_days):
        days_since = (date.today() - date.fromisoformat(state["last_run_date"])).days
        logger.info(
            "Not due yet. Last run %d day(s) ago (interval: %d). Use --force to override.",
            days_since,
            interval_days,
        )
        return

    token = get_github_token()
    client = GithubClient(token)

    try:
        user = client.get_authenticated_user()
    except GithubAPIError as exc:
        logger.error("Failed to authenticate: %s", exc)
        return

    username: str = user["login"]
    logger.info("Authenticated as: %s", username)

    try:
        existing_repos = client.list_user_repos(username)
        existing_names: set[str] = {r["name"] for r in existing_repos}
    except GithubAPIError as exc:
        logger.error("Failed to list repos: %s", exc)
        return

    idea = generate_project_idea(cfg, used_names)
    if idea is None:
        logger.error("Could not generate a unique project idea.")
        return

    project_name = make_unique_name(idea["name"], existing_names | used_names)
    description = idea["description"]
    language = random.choice(language_pool)

    logger.info(
        "Creating project '%s' (%s): %s", project_name, language, description
    )

    # Create repository WITHOUT auto_init so we fully control all file content
    try:
        repo_data = client.create_repo(
            name=project_name,
            description=description,
            private=private_repos,
            auto_init=False,
        )
    except GithubAPIError as exc:
        logger.error("Failed to create repository '%s': %s", project_name, exc)
        return

    repo_url: str = repo_data.get("html_url", "")
    logger.info("Repository created: %s", repo_url)

    # GitHub needs a moment before the Contents API accepts writes on a new repo
    time.sleep(2)


    branch = "main"
    if not initialise_branch(client, username, project_name, branch, project_name, description, language):
        logger.error("Could not initialise branch — aborting file seeding.")

        created_projects.append(project_name)
        save_state(STATE_FILE, {
            "last_run_date": str(date.today()),
            "last_run_ts": datetime.now(timezone.utc).isoformat(),
            "created_projects": created_projects,
            "last_project": project_name,
            "last_language": language,
            "last_repo_url": repo_url,
        })
        return

    time.sleep(1)

    # Seed remaining required + optional files
    # README.md was already pushed as the init commit; seed_repository will
    # detect its SHA and update it with the full rendered content.
    all_ok, failed = seed_repository(
        client=client,
        owner=username,
        repo_name=project_name,
        project_name=project_name,
        description=description,
        language=language,
        branch=branch,
    )

    if not all_ok:
        logger.error(
            "Required file(s) missing after seeding: %s. "
            "Check the logs above for per-file errors.",
            failed,
        )
    else:
        logger.info("All required files seeded successfully.")

    # Persist state regardless 
    created_projects.append(project_name)
    new_state = {
        "last_run_date": str(date.today()),
        "last_run_ts": datetime.now(timezone.utc).isoformat(),
        "created_projects": created_projects,
        "last_project": project_name,
        "last_language": language,
        "last_repo_url": repo_url,
        "last_seed_ok": all_ok,
    }
    save_state(STATE_FILE, new_state)
    logger.info(
        "Done. Project '%s' created at %s. State saved.", project_name, repo_url
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Project Creator Agent — generates stub projects on your GitHub account."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the scheduling interval guard (useful for testing).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(force=args.force)