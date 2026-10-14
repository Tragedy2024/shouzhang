"""Provider settings stay local and separate when switching text services."""

import json

import config


def test_provider_setting_uses_default_without_private_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "__file__", str(tmp_path / "config.py"))
    monkeypatch.delenv("TEXT_MODEL", raising=False)
    assert config._provider_setting("TEXT_MODEL", "deepseek-flash") == "deepseek-flash"


def test_text_settings_do_not_reuse_vision_key(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "__file__", str(tmp_path / "config.py"))
    for name in ("TEXT_API_KEY", "VISION_API_KEY", "TEXT_MODEL", "TEXT_API_URL"):
        monkeypatch.delenv(name, raising=False)
    instance = tmp_path / "instance"
    instance.mkdir()
    (instance / "provider-secrets.json").write_text(json.dumps({
        "TEXT_API_KEY": "offline-text-token",
        "VISION_API_KEY": "offline-vision-token",
        "TEXT_MODEL": "private-model",
        "TEXT_API_URL": "https://example.invalid/chat/completions",
    }))
    assert config._provider_setting("TEXT_API_KEY") == "offline-text-token"
    assert config._provider_setting("VISION_API_KEY") == "offline-vision-token"
    assert config._provider_setting("TEXT_MODEL", "deepseek-flash") == "private-model"
    assert config._provider_setting("TEXT_API_URL") == "https://example.invalid/chat/completions"


def test_environment_takes_precedence_over_private_config(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "__file__", str(tmp_path / "config.py"))
    instance = tmp_path / "instance"
    instance.mkdir()
    (instance / "provider-secrets.json").write_text(json.dumps({"TEXT_MODEL": "private-model"}))
    monkeypatch.setenv("TEXT_MODEL", "environment-model")
    assert config._provider_setting("TEXT_MODEL", "deepseek-flash") == "environment-model"
