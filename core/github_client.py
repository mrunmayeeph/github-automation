from __future__ import annotations

import base64
import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"
DEFAULT_TIMEOUT = 20  #seconds


class GithubAPIError(Exception):
    """Raised when the GitHub API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GithubClient:
    """Stateless GitHub REST API v3 client.

    Args:
        token: Personal Access Token with `repo` scope.
    """

    def __init__(self, token: str) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "github-activity-bot/1.0",
            }
        )

    #Internal helpers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Execute an HTTP request and return the parsed JSON body.

        Retries once on transient 5xx errors with a short back-off.

        Raises:
            GithubAPIError: for non-2xx responses after retries.
            requests.exceptions.RequestException: for network-level failures.
        """
        url = f"{BASE_URL}{path}"
        for attempt in (1, 2):
            try:
                response = self._session.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    timeout=DEFAULT_TIMEOUT,
                )
            except requests.exceptions.Timeout:
                raise GithubAPIError(f"Request timed out: {method} {url}")
            except requests.exceptions.ConnectionError as exc:
                raise GithubAPIError(f"Network error: {exc}")

            if response.status_code in (200, 201, 204):
                if response.content:
                    return response.json()
                return {}

            if response.status_code >= 500 and attempt == 1:
                logger.warning(
                    "GitHub API returned %s — retrying in 5 s.", response.status_code
                )
                time.sleep(5)
                continue

            # 4xx or second 5xx
            try:
                detail = response.json().get("message", response.text)
            except Exception:
                detail = response.text
            raise GithubAPIError(
                f"GitHub API error {response.status_code}: {detail}",
                status_code=response.status_code,
            )

        # Should never reach here but satisfies type checkers
        raise GithubAPIError("Request failed after retries.")

    # User

    def get_authenticated_user(self) -> dict[str, Any]:
        """Return the authenticated user's profile."""
        return self._request("GET", "/user") 

    # Repositories

    def list_user_repos(self, username: str) -> list[dict[str, Any]]:
        """Return all non-forked, non-archived repos for *username*.

        Handles pagination automatically (up to 1 000 repos).
        """
        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            page_data = self._request(
                "GET",
                f"/users/{username}/repos",
                params={"type": "owner", "per_page": 100, "page": page},
            )
            if not isinstance(page_data, list):
                break
            if not page_data:
                break
            repos.extend(page_data)
            if len(page_data) < 100:
                break
            page += 1

        return [
            r for r in repos
            if not r.get("fork") and not r.get("archived")
        ]

    def create_repo(
        self,
        name: str,
        description: str = "",
        private: bool = False,
        auto_init: bool = False,
    ) -> dict[str, Any]:
        """Create a new repository under the authenticated user's account."""
        return self._request(  
            "POST",
            "/user/repos",
            json_body={
                "name": name,
                "description": description,
                "private": private,
                "auto_init": auto_init,
            },
        )

    # Contents API

    def get_file(self, owner: str, repo: str, file_path: str) -> dict[str, Any] | None:
        """Return file metadata (including SHA and content) or None if absent."""
        try:
            result = self._request("GET", f"/repos/{owner}/{repo}/contents/{file_path}")
            return result  
        except GithubAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

    def create_or_update_file(
        self,
        owner: str,
        repo: str,
        file_path: str,
        content: str,
        commit_message: str,
        sha: str | None = None,
        branch: str = "main",
    ) -> dict[str, Any]:
        """Create or update a file via the Contents API.

        Args:
            sha: Current blob SHA (required for updates, omit for creates).
        """
        encoded = base64.b64encode(content.encode()).decode()
        body: dict[str, Any] = {
            "message": commit_message,
            "content": encoded,
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        return self._request(  
            "PUT",
            f"/repos/{owner}/{repo}/contents/{file_path}",
            json_body=body,
        )

    def get_default_branch(self, owner: str, repo: str) -> str:
        """Return the default branch name for a repository."""
        data = self._request("GET", f"/repos/{owner}/{repo}")
        return data.get("default_branch", "main") 