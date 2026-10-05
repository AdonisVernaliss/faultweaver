import importlib

import pytest

from faultweaver.storage.keys import KeyMaterial, MemoryKeyProvider


@pytest.fixture(autouse=True)
def isolated_storage_key(monkeypatch):
    """Backend test applications use encryption without touching an OS key store."""
    provider = MemoryKeyProvider(KeyMaterial.generate())
    module = importlib.import_module("faultweaver.app")
    monkeypatch.setattr(module, "key_provider_for", lambda settings: provider)
    return provider
