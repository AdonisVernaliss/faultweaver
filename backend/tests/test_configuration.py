import pytest

from faultweaver.config import Settings
from faultweaver.storage.keys import StorageError


def test_configuration_defaults_are_local(monkeypatch):
    for name in ("FAULTWEAVER_ALLOWED_ORIGINS", "FAULTWEAVER_KEYRING_ACCOUNT"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_environment()
    assert settings.allowed_origins == ("http://localhost:5173",)
    assert settings.keyring_account == "local-storage-v1"


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "file:///local",
        "https://user:secret@example.test",
        "https://example.test/path",
        "https://example.test?token=private",
        "http://example.test:bad",
        "http://example.test#fragment",
    ],
)
def test_invalid_origin_config_fails_without_echoing_values(monkeypatch, origin):
    monkeypatch.setenv("FAULTWEAVER_ALLOWED_ORIGINS", origin)
    with pytest.raises(StorageError, match="Origins must be explicit HTTP") as error:
        Settings.from_environment()
    assert origin not in str(error.value)


def test_empty_key_account_fails_safely(monkeypatch):
    monkeypatch.setenv("FAULTWEAVER_KEYRING_ACCOUNT", " ")
    with pytest.raises(StorageError, match="key-store account"):
        Settings.from_environment()


def test_explicit_origin_and_disabled_browser_cors(monkeypatch):
    monkeypatch.setenv(
        "FAULTWEAVER_ALLOWED_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173"
    )
    assert len(Settings.from_environment().allowed_origins) == 2
    monkeypatch.setenv("FAULTWEAVER_ALLOWED_ORIGINS", "")
    assert Settings.from_environment().allowed_origins == ()
