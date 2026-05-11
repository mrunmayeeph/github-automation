
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.daily_commit import (
    already_ran_today,
    build_tracking_line,
    select_target_repo,
)

# already_ran_today

class TestAlreadyRanToday:
    def test_returns_true_when_date_matches_today(self):
        state = {"last_run_date": str(date.today())}
        assert already_ran_today(state) is True

    def test_returns_false_when_date_is_yesterday(self):
        from datetime import timedelta
        yesterday = str(date.today() - timedelta(days=1))
        state = {"last_run_date": yesterday}
        assert already_ran_today(state) is False

    def test_returns_false_when_state_is_empty(self):
        assert already_ran_today({}) is False

    def test_returns_false_when_last_run_date_is_none(self):
        assert already_ran_today({"last_run_date": None}) is False

    def test_returns_false_when_date_key_missing(self):
        state = {"last_repo": "my-repo"}
        assert already_ran_today(state) is False


# select_target_repo

def _make_repos(names: list[str]) -> list[dict]:
    return [{"name": n, "fork": False, "archived": False} for n in names]


class TestSelectTargetRepo:
    def test_raises_when_no_repos(self):
        with pytest.raises(ValueError, match="No eligible repositories"):
            select_target_repo([], last_repo=None)

    def test_returns_single_repo_even_if_it_was_last(self):
        repos = _make_repos(["only-repo"])
        chosen = select_target_repo(repos, last_repo="only-repo")
        assert chosen["name"] == "only-repo"

    def test_avoids_last_repo_when_alternatives_exist(self):
        repos = _make_repos(["repo-a", "repo-b", "repo-c"])
        # Run 200 times — last_repo must never be chosen
        for _ in range(200):
            chosen = select_target_repo(repos, last_repo="repo-a")
            assert chosen["name"] != "repo-a"

    def test_selects_from_all_when_last_repo_is_none(self):
        repos = _make_repos(["repo-x", "repo-y"])
        names_chosen: set[str] = set()
        for _ in range(100):
            names_chosen.add(select_target_repo(repos, last_repo=None)["name"])
        # Both repos should eventually be selected
        assert names_chosen == {"repo-x", "repo-y"}

    def test_selects_from_all_when_last_repo_not_in_list(self):
        repos = _make_repos(["repo-1", "repo-2"])
        chosen = select_target_repo(repos, last_repo="deleted-repo")
        assert chosen["name"] in {"repo-1", "repo-2"}

    def test_returns_dict_with_name_key(self):
        repos = _make_repos(["my-repo"])
        result = select_target_repo(repos, last_repo=None)
        assert "name" in result


# build_tracking_line


class TestBuildTrackingLine:
    def test_contains_commit_index(self):
        line = build_tracking_line(5)
        assert "5" in line

    def test_ends_with_newline(self):
        line = build_tracking_line(1)
        assert line.endswith("\n")

    def test_contains_iso_timestamp(self):
        import re
        line = build_tracking_line(1)
        # Should have a pattern like 2024-01-15T12:34:56Z
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", line)

    def test_different_indices_produce_different_lines(self):
        line1 = build_tracking_line(1)
        line2 = build_tracking_line(2)
        # Content differs (index embedded in both)
        assert line1 != line2