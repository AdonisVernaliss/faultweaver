from sqlalchemy import Engine, inspect, text

from faultweaver.migrations.runner import upgrade_database
from faultweaver.storage.database import check_integrity
from faultweaver.storage.keys import KeyMaterial, StorageError


def prepare_storage(engine: Engine, database_url: str, key: KeyMaterial) -> None:
    with engine.begin() as connection:
        check_integrity(connection.connection.driver_connection)
        if "storage_metadata" in inspect(connection).get_table_names():
            rows = connection.execute(text("SELECT * FROM storage_metadata")).mappings().all()
            if rows and (
                len(rows) != 1
                or rows[0]["id"] != 1
                or rows[0]["policy_version"] != 1
                or rows[0]["cipher_format"] != 4
            ):
                raise StorageError("Unsupported protected-storage policy version")
            if rows and rows[0]["key_id"] != key.key_id:
                raise StorageError("Storage key identity does not match this database")
        upgrade_database(database_url, connection=connection)
        existing = connection.scalar(text("SELECT count(*) FROM storage_metadata"))
        if not existing:
            connection.execute(
                text("INSERT INTO storage_metadata VALUES (1, 1, 4, :key_id)"),
                {"key_id": key.key_id},
            )
