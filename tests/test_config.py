"""WATCH_DETAIL / WATCH_TRANSCRIBER resolution and frame_cap mapping."""
from __future__ import annotations

import config


def test_default_detail_is_transcript(monkeypatch, tmp_path):
    """Frames are opt-in: the default run transcribes and extracts none."""
    monkeypatch.delenv("WATCH_DETAIL", raising=False)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "missing.env")
    assert config.get_config()["detail"] == "transcript"


def test_env_overrides_detail(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCH_DETAIL", "efficient")
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "missing.env")
    assert config.get_config()["detail"] == "efficient"


def test_invalid_detail_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCH_DETAIL", "bogus")
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "missing.env")
    assert config.get_config()["detail"] == config.DEFAULT_DETAIL


def test_default_transcriber_is_auto(monkeypatch, tmp_path):
    monkeypatch.delenv("WATCH_TRANSCRIBER", raising=False)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "missing.env")
    assert config.get_config()["transcriber"] == "auto"


def test_env_overrides_transcriber(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCH_TRANSCRIBER", "deepinfra-whisper")
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "missing.env")
    assert config.get_config()["transcriber"] == "deepinfra-whisper"


def test_every_provider_is_an_accepted_transcriber():
    """TRANSCRIBERS is derived from asr.PROVIDERS; guard the derivation so a
    provider added to the registry can never be rejected by config validation."""
    import asr

    assert config.TRANSCRIBERS == {"auto", *asr.PROVIDERS}
    assert set(asr.PREFERENCE) <= set(asr.PROVIDERS)


def test_invalid_transcriber_falls_back_to_auto(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCH_TRANSCRIBER", "bogus")
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "missing.env")
    assert config.get_config()["transcriber"] == "auto"


def test_get_config_keys(monkeypatch, tmp_path):
    monkeypatch.delenv("WATCH_DETAIL", raising=False)
    monkeypatch.delenv("WATCH_TRANSCRIBER", raising=False)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "missing.env")
    cfg = config.get_config()
    assert set(cfg) == {"detail", "transcriber", "notes_dir", "config_file"}


def test_notes_dir_defaults_and_expands(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("WATCH_NOTES_DIR", raising=False)
    assert config.get_config()["notes_dir"] == config.DEFAULT_NOTES_DIR

    monkeypatch.setenv("WATCH_NOTES_DIR", "~/elsewhere")
    resolved = config.get_config()["notes_dir"]
    assert resolved.is_absolute() and resolved.name == "elsewhere"


def test_frame_cap_mapping():
    assert config.frame_cap("efficient") == 50
    assert config.frame_cap("balanced") == 100
    assert config.frame_cap("token-burner") is None
    assert config.frame_cap("transcript") is None
    assert config.frame_cap("anything-else") == 100
