from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from faultweaver.database import Base


class StorageMetadata(Base):
    __tablename__ = "storage_metadata"
    __table_args__ = (CheckConstraint("id = 1", name="ck_storage_metadata_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_version: Mapped[int] = mapped_column(Integer)
    cipher_format: Mapped[int] = mapped_column(Integer)
    key_id: Mapped[str] = mapped_column(String(32))
