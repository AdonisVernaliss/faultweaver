import base64
import json
import os
import secrets
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from faultweaver.app import create_app
from faultweaver.config import Settings
from faultweaver.http_traffic.models import HttpExchange
from faultweaver.identities.models import Identity
from faultweaver.migrations.runner import upgrade_database
from faultweaver.storage.cli import main
from faultweaver.storage.configuration import key_provider_for
from faultweaver.storage.database import check_integrity, open_database
from faultweaver.storage.keys import FileKeyProvider, KeyMaterial, MemoryKeyProvider, StorageError
from faultweaver.storage.locking import storage_lock
from faultweaver.storage.migration import logical_fingerprint, migrate_plaintext
from tests.test_engagements_and_scope import create_engagement
from tests.test_http_import import authorize


def settings_for(path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{path}", allowed_origins=())


def seed_legacy(path: Path, marker: str) -> None:
    path.parent.mkdir()
    url = f"sqlite:///{path}"
    upgrade_database(url, "0006")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO engagements (id, name, description, status, created_at, updated_at) "
                "VALUES ('legacy', 'Migration fixture', :marker, 'active', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"marker": marker},
        )
    with Session(engine) as session:
        session.add(
            Identity(
                id="legacy-identity",
                engagement_id="legacy",
                name="Legacy context",
                bearer_token=marker + "-bearer",
                cookies=[{"name": "session", "value": marker + "-cookie"}],
            )
        )
        session.add(
            HttpExchange(
                id="legacy-request",
                engagement_id="legacy",
                source="raw_import",
                method="POST",
                url="http://app.test/api/session?access_token=" + marker,
                host="app.test",
                path="/api/session",
                query="access_token=" + marker,
                request_headers=[{"name": "Authorization", "value": "Bearer " + marker}],
                request_body=json.dumps({"password": marker + "-password"}),
                response_status=200,
                response_headers=[{"name": "Set-Cookie", "value": "session=" + marker}],
                response_body=json.dumps({"private_record": marker + "-response"}),
            )
        )
        session.commit()
    engine.dispose()


def test_legacy_migration_verifies_rows_backup_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "data" / "legacy.db"
    backup = tmp_path / "backups" / "legacy.db"
    marker = secrets.token_urlsafe(40)
    key = KeyMaterial.generate()
    seed_legacy(path, marker)
    with closing(sqlite3.connect(path)) as legacy:
        legacy.execute("PRAGMA journal_mode=WAL")
        legacy.execute("UPDATE engagements SET description=?", (marker,))
        legacy.commit()
    with closing(sqlite3.connect(path)) as original:
        before = logical_fingerprint(original)
    with (
        pytest.raises(StorageError, match="explicit storage migration"),
        TestClient(create_app(settings_for(path), key_provider=MemoryKeyProvider(key))),
    ):
        pass
    counts = migrate_plaintext(path, key, backup)
    assert counts["engagements"] == 1
    assert backup.stat().st_mode & 0o777 == 0o600
    with closing(sqlite3.connect(backup)) as saved:
        assert logical_fingerprint(saved) == before
    with closing(open_database(path, key)) as protected:
        assert logical_fingerprint(protected) == before
        check_integrity(protected)
    assert marker.encode() not in path.read_bytes()
    assert not any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))
    assert migrate_plaintext(path, key, backup) == {}
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    with TestClient(
        create_app(
            settings_for(path),
            key_provider=MemoryKeyProvider(key),
            http_transport=httpx.MockTransport(respond),
        )
    ) as client:
        assert client.get("/api/engagements/legacy").json()["description"] == marker
        authorize(client, "legacy")
        identities = client.get("/api/engagements/legacy/identities").json()
        assert marker not in json.dumps(identities)
        detail = client.get("/api/requests/legacy-request").json()
        assert marker + "-password" not in detail["request_body"]
        assert marker not in detail["url"]
        assert (
            client.post(
                "/api/requests/legacy-request/replay", json={"identity_id": "legacy-identity"}
            ).status_code
            == 201
        )
        assert seen[0].headers["authorization"] == "Bearer " + marker + "-bearer"
        assert marker + "-cookie" in seen[0].headers["cookie"]
        assert json.loads(seen[0].content)["password"] == marker + "-password"
        assert (
            client.post(
                "/api/engagements/legacy/traffic/raw",
                json={
                    "base_url": "http://app.test",
                    "raw": "GET /api/another HTTP/1.1\r\nHost: app.test\r\n\r\n",
                },
            ).status_code
            == 201
        )
        with client.app.state.session_factory() as session:
            assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0007"


def test_failed_replacement_preserves_original_and_can_retry(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "data" / "legacy.db"
    seed_legacy(path, secrets.token_urlsafe(40))
    original = path.read_bytes()
    key = KeyMaterial.generate()
    backup = tmp_path / "backup" / "first.db"
    replace = os.replace
    monkeypatch.setattr(
        "faultweaver.storage.migration.os.replace", lambda *_: (_ for _ in ()).throw(OSError())
    )
    with pytest.raises(StorageError, match="migration failed"):
        migrate_plaintext(path, key, backup)
    assert path.read_bytes() == backup.read_bytes() == original
    assert not list(path.parent.glob(".storage-conversion-*"))
    monkeypatch.setattr("faultweaver.storage.migration.os.replace", replace)
    with pytest.raises(StorageError, match="already exists"):
        migrate_plaintext(path, key, backup)
    migrate_plaintext(path, key, tmp_path / "backup" / "retry.db")
    with closing(open_database(path, key)) as protected:
        check_integrity(protected)


def test_migration_refuses_unsafe_backup_and_active_storage(tmp_path: Path) -> None:
    path = tmp_path / "data" / "legacy.db"
    seed_legacy(path, "synthetic legacy content")
    key = KeyMaterial.generate()
    before = path.read_bytes()
    with pytest.raises(StorageError, match="separate"):
        migrate_plaintext(path, key, path.parent / "backup.db")
    with storage_lock(path), pytest.raises(StorageError, match="busy"):
        migrate_plaintext(path, key, tmp_path / "backup.db")
    assert path.read_bytes() == before


def test_live_identity_replay_raw_byte_scan_and_stolen_copy(tmp_path: Path, caplog) -> None:
    path = tmp_path / "data" / "protected.db"
    key = KeyMaterial.generate()
    markers = [secrets.token_urlsafe(40) for _ in range(10)]
    observed = []

    def handler(request):
        observed.append(request)
        return httpx.Response(
            200,
            headers={"set-cookie": "session=" + markers[8]},
            json={"password": markers[6], "private_record": markers[7]},
        )

    kwargs = {
        "key_provider": MemoryKeyProvider(key),
        "http_transport": httpx.MockTransport(handler),
    }
    with TestClient(create_app(settings_for(path), **kwargs)) as client:
        engagement = create_engagement(client)
        authorize(client, engagement)
        identity = client.post(
            f"/api/engagements/{engagement}/identities",
            json={
                "name": "Protected synthetic identity",
                "bearer_token": markers[0],
                "api_key_header": "X-API-Key",
                "api_key_value": markers[1],
                "cookies": [{"name": "session", "value": markers[2]}],
                "custom_headers": [{"name": "X-Custom-Secret", "value": markers[3]}],
            },
        )
        assert identity.status_code == 201
        raw = (
            f"POST /api/private/{markers[9]}?access_token={markers[4]} HTTP/1.1\r\n"
            "Host: app.test\r\nContent-Type: application/json\r\n\r\n"
            + json.dumps({"password": markers[5]})
        )
        imported = client.post(
            f"/api/engagements/{engagement}/traffic/raw",
            json={
                "base_url": "http://app.test",
                "raw": raw,
            },
        ).json()
        replay = client.post(
            f"/api/requests/{imported['id']}/replay",
            json={
                "identity_id": identity.json()["id"],
            },
        )
        assert replay.status_code == 201
        assert observed[-1].headers["authorization"] == "Bearer " + markers[0]
        assert observed[-1].headers["x-api-key"] == markers[1]
        assert markers[2] in observed[-1].headers["cookie"]
        assert observed[-1].headers["x-custom-secret"] == markers[3]
        assert json.loads(observed[-1].content)["password"] == markers[5]
        assert markers[0] not in identity.text
        assert markers[5] not in replay.text and markers[6] not in replay.text
        # Exercise live encrypted WAL and the rollback journal, including deleted pages.
        with closing(open_database(path, key)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE byte_scan (value TEXT)")
            db.execute("INSERT INTO byte_scan VALUES (?)", (markers[7] * 1000,))
            db.commit()
            for artifact in path.parent.iterdir():
                data = artifact.read_bytes()
                assert all(value.encode() not in data for value in markers)
                assert key.secret not in data and key.secret.hex().encode() not in data
                assert base64.b64encode(key.secret) not in data
                assert key.serialize().encode() not in data
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("DELETE FROM byte_scan")
            for artifact in path.parent.iterdir():
                assert all(value.encode() not in artifact.read_bytes() for value in markers)
            db.commit()
    for artifact in path.parent.iterdir():
        assert all(value.encode() not in artifact.read_bytes() for value in markers)
    assert all(value not in caplog.text for value in markers)
    stolen = tmp_path / "stolen.db"
    shutil.copyfile(path, stolen)
    before = stolen.read_bytes()
    with pytest.raises(sqlite3.DatabaseError), closing(sqlite3.connect(stolen)) as db:
        db.execute("SELECT * FROM identities").fetchall()
    with (
        pytest.raises(StorageError),
        TestClient(
            create_app(
                settings_for(stolen),
                key_provider=MemoryKeyProvider(KeyMaterial.generate()),
            )
        ),
    ):
        pass
    assert stolen.read_bytes() == before
    with TestClient(create_app(settings_for(stolen), **kwargs)) as client:
        assert client.get(f"/api/requests/{imported['id']}").status_code == 200
        assert (
            client.post(
                f"/api/requests/{imported['id']}/replay",
                json={
                    "identity_id": identity.json()["id"],
                },
            ).status_code
            == 201
        )


@pytest.mark.parametrize(
    "field,value", [("policy_version", 99), ("cipher_format", 3), ("key_id", "wrong")]
)
def test_storage_policy_mismatch_never_reinitializes(tmp_path: Path, field, value) -> None:
    path = tmp_path / "protected.db"
    key = KeyMaterial.generate()
    with TestClient(create_app(settings_for(path), key_provider=MemoryKeyProvider(key))):
        pass
    with closing(open_database(path, key)) as db:
        db.execute(f"UPDATE storage_metadata SET {field}=?", (value,))
        db.commit()
    before = path.read_bytes()
    with (
        pytest.raises(StorageError),
        TestClient(
            create_app(
                settings_for(path),
                key_provider=MemoryKeyProvider(key),
            )
        ),
    ):
        pass
    assert path.read_bytes() == before


def test_cli_key_initialization_and_fail_closed_configuration(tmp_path: Path, monkeypatch, capsys):
    path = tmp_path / "data" / "new.db"
    keyfile = tmp_path / "keys" / "master.json"
    monkeypatch.setenv("FAULTWEAVER_DATABASE_URL", f"sqlite:///{path}")
    monkeypatch.setenv("FAULTWEAVER_KEY_PROVIDER", "file")
    monkeypatch.setenv("FAULTWEAVER_MASTER_KEY_FILE", str(keyfile))
    assert main(["init-key"]) == 0
    key = FileKeyProvider(keyfile, path).load()
    assert main(["init-key"]) == 1
    assert keyfile.read_text().strip() == key.serialize()
    assert key.serialize() not in capsys.readouterr().out
    export = tmp_path / "recovery" / "key.json"
    assert main(["backup-key", "--output", str(export)]) == 0
    assert FileKeyProvider(export, path).load().secret == key.secret
    assert main(["backup-key", "--output", str(export)]) == 1
    monkeypatch.setenv("FAULTWEAVER_KEY_PROVIDER", "native")
    with pytest.raises(StorageError):
        key_provider_for(Settings.from_environment())
    monkeypatch.setenv("FAULTWEAVER_KEY_PROVIDER", "plaintext")
    with pytest.raises(StorageError):
        key_provider_for(Settings.from_environment())


def test_missing_provider_key_never_creates_or_replaces_database(tmp_path: Path):
    path = tmp_path / "data" / "protected.db"
    missing = FileKeyProvider(tmp_path / "absent-key.json", path)
    with (
        pytest.raises(StorageError),
        TestClient(create_app(settings_for(path), key_provider=missing)),
    ):
        pass
    assert not path.exists()
    key = KeyMaterial.generate()
    with TestClient(create_app(settings_for(path), key_provider=MemoryKeyProvider(key))):
        pass
    before = path.read_bytes()
    with (
        pytest.raises(StorageError),
        TestClient(create_app(settings_for(path), key_provider=missing)),
    ):
        pass
    assert path.read_bytes() == before
