
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.project_creator import (
    fetch_ai_idea,
    generate_project_idea,
    is_due,
    make_unique_name,
    pick_builtin_idea,
)
from agents.project_templates import BUILTIN_IDEAS


# is_due


class TestIsDue:
    def test_due_when_state_is_empty(self):
        assert is_due({}, interval_days=7) is True

    def test_due_when_last_run_date_missing(self):
        assert is_due({"created_projects": []}, interval_days=7) is True

    def test_not_due_when_ran_today(self):
        state = {"last_run_date": str(date.today())}
        assert is_due(state, interval_days=7) is False

    def test_not_due_when_ran_3_days_ago_with_7_day_interval(self):
        three_days_ago = str(date.today() - timedelta(days=3))
        state = {"last_run_date": three_days_ago}
        assert is_due(state, interval_days=7) is False

    def test_due_when_interval_exceeded(self):
        eight_days_ago = str(date.today() - timedelta(days=8))
        state = {"last_run_date": eight_days_ago}
        assert is_due(state, interval_days=7) is True

    def test_due_exactly_on_interval_boundary(self):
        exactly = str(date.today() - timedelta(days=7))
        state = {"last_run_date": exactly}
        assert is_due(state, interval_days=7) is True

    def test_handles_corrupt_date_gracefully(self):
        state = {"last_run_date": "not-a-date"}
        # Should treat as "never ran" and return True
        assert is_due(state, interval_days=7) is True


# make_unique_name


class TestMakeUniqueName:
    def test_returns_base_name_when_not_taken(self):
        result = make_unique_name("my-project", existing_repo_names=set())
        assert result == "my-project"

    def test_appends_suffix_when_name_taken(self):
        result = make_unique_name("my-project", existing_repo_names={"my-project"})
        assert result == "my-project-2"

    def test_increments_suffix_until_unique(self):
        taken = {"my-project", "my-project-2", "my-project-3"}
        result = make_unique_name("my-project", existing_repo_names=taken)
        assert result == "my-project-4"

    def test_empty_existing_set(self):
        result = make_unique_name("hello", existing_repo_names=set())
        assert result == "hello"


# pick_builtin_idea

class TestPickBuiltinIdea:
    def test_returns_idea_when_pool_has_items(self):
        result = pick_builtin_idea(used_names=set())
        assert result is not None
        assert "name" in result
        assert "description" in result

    def test_avoids_used_names(self):
        all_names = {i["name"] for i in BUILTIN_IDEAS}
        # Exhaust all but one
        last_name = list(all_names)[-1]
        used = all_names - {last_name}
        result = pick_builtin_idea(used_names=used)
        assert result is not None
        assert result["name"] == last_name

    def test_returns_none_when_all_used(self):
        all_names = {i["name"] for i in BUILTIN_IDEAS}
        result = pick_builtin_idea(used_names=all_names)
        assert result is None


# fetch_ai_idea :graceful fallback when API is unavailable

class TestFetchAiIdea:
    def test_returns_none_when_endpoint_missing(self):
        ai_cfg = {"enabled": True, "endpoint": "", "timeout_seconds": 5}
        result = fetch_ai_idea(ai_cfg)
        assert result is None

    def test_returns_none_when_token_missing(self):
        ai_cfg = {
            "enabled": True,
            "endpoint": "https://api-inference.huggingface.co/models/test",
            "timeout_seconds": 5,
        }
        with patch.dict("os.environ", {}, clear=True):
            # No HUGGINGFACE_API_TOKEN set
            result = fetch_ai_idea(ai_cfg)
        assert result is None

    def test_returns_none_on_network_error(self):
        import requests as req

        ai_cfg = {
            "enabled": True,
            "endpoint": "https://api-inference.huggingface.co/models/test",
            "timeout_seconds": 5,
        }
        with patch.dict("os.environ", {"HUGGINGFACE_API_TOKEN": "fake-token"}):
            with patch("requests.Session.request", side_effect=req.exceptions.ConnectionError("down")):
                with patch("requests.post", side_effect=req.exceptions.ConnectionError("down")):
                    result = fetch_ai_idea(ai_cfg)
        assert result is None

    def test_returns_none_on_malformed_json_response(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [{"generated_text": "this is not json at all"}]

        ai_cfg = {
            "enabled": True,
            "endpoint": "https://api-inference.huggingface.co/models/test",
            "timeout_seconds": 5,
        }
        with patch.dict("os.environ", {"HUGGINGFACE_API_TOKEN": "fake-token"}):
            with patch("requests.post", return_value=mock_resp):
                result = fetch_ai_idea(ai_cfg)
        assert result is None


# generate_project_idea

class TestGenerateProjectIdea:
    def test_falls_back_to_builtin_when_ai_disabled(self):
        cfg = {"project_creator": {"ai_api": {"enabled": False}}}
        result = generate_project_idea(cfg, used_names=set())
        assert result is not None
        assert "name" in result

    def test_skips_already_used_ai_names_and_falls_back(self):
        cfg = {"project_creator": {"ai_api": {"enabled": True, "endpoint": "http://x", "timeout_seconds": 5}}}
        used = {i["name"] for i in BUILTIN_IDEAS}  # exhaust all builtins

        # AI returns a name that's also used
        with patch("agents.project_creator.fetch_ai_idea", return_value={"name": list(used)[0], "description": "test"}):
            result = generate_project_idea(cfg, used_names=used)
        # All builtins exhausted AND ai name is used → should return None
        assert result is None