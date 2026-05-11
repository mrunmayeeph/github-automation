
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import is_kill_switch_active, load_config
from core.state import load_state, save_state


# Config

class TestLoadConfig:
    def test_raises_when_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_raises_on_invalid_yaml(self, tmp_path):
        bad_yaml = tmp_path / "config.yaml"
        bad_yaml.write_text(": : :")
        import yaml
        with pytest.raises((yaml.YAMLError, ValueError)):
            load_config(bad_yaml)

    def test_loads_valid_config(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("kill_switch: false\ndaily_commit:\n  min_commits: 1\n")
        cfg = load_config(cfg_file)
        assert cfg["kill_switch"] is False
        assert cfg["daily_commit"]["min_commits"] == 1


class TestIsKillSwitchActive:
    def test_true_when_flag_set(self):
        assert is_kill_switch_active({"kill_switch": True}) is True

    def test_false_when_flag_not_set(self):
        assert is_kill_switch_active({"kill_switch": False}) is False

    def test_false_when_key_missing(self):
        assert is_kill_switch_active({}) is False

    def test_false_for_truthy_non_bool(self):
        # String "false" is truthy in Python — config should use proper YAML booleans.
        # This test documents the behaviour: a non-empty string is truthy.
        assert is_kill_switch_active({"kill_switch": "false"}) is True


# State persistence


class TestStatePersistence:
    def test_save_and_load_round_trip(self, tmp_path, monkeypatch):
        import core.state as state_module
        monkeypatch.setattr(state_module, "STATE_DIR", tmp_path)

        data = {"last_run_date": "2024-01-01", "last_repo": "my-repo", "count": 42}
        save_state("test_state.json", data)
        loaded = load_state("test_state.json")
        assert loaded == data

    def test_load_returns_empty_dict_when_file_missing(self, tmp_path, monkeypatch):
        import core.state as state_module
        monkeypatch.setattr(state_module, "STATE_DIR", tmp_path)

        result = load_state("does_not_exist.json")
        assert result == {}

    def test_load_returns_empty_dict_on_corrupt_json(self, tmp_path, monkeypatch):
        import core.state as state_module
        monkeypatch.setattr(state_module, "STATE_DIR", tmp_path)

        bad_file = tmp_path / "corrupt.json"
        bad_file.write_text("{not valid json}")
        result = load_state("corrupt.json")
        assert result == {}

    def test_save_creates_directory_if_missing(self, tmp_path, monkeypatch):
        import core.state as state_module
        nested = tmp_path / "a" / "b" / "c"
        monkeypatch.setattr(state_module, "STATE_DIR", nested)

        save_state("x.json", {"hello": "world"})
        assert (nested / "x.json").exists()

    def test_overwrite_existing_state(self, tmp_path, monkeypatch):
        import core.state as state_module
        monkeypatch.setattr(state_module, "STATE_DIR", tmp_path)

        save_state("s.json", {"v": 1})
        save_state("s.json", {"v": 2})
        result = load_state("s.json")
        assert result["v"] == 2