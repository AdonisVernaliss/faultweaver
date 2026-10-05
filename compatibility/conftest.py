import importlib

import pytest
from faultweaver.storage.keys import KeyMaterial, MemoryKeyProvider


@pytest.fixture(autouse=True)
def isolated_storage_key(monkeypatch):
    """Compatibility applications use an explicit, ephemeral key per workflow."""
    provider = MemoryKeyProvider(KeyMaterial.generate())
    module = importlib.import_module("faultweaver.app")
    monkeypatch.setattr(module, "key_provider_for", lambda settings: provider)
    return provider
