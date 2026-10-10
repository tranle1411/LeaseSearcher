"""Versioned PostgreSQL persistence; the immutable snapshot is the fallback."""

import os
from pathlib import Path

from sqlalchemy import JSON, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.schemas import Dataset


class Base(DeclarativeBase):
    pass


class Snapshot(Base):
    __tablename__ = "dataset_snapshots"
    version: Mapped[str] = mapped_column(String(80), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


def engine_for(url):
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})


def read_snapshot():
    return Dataset.model_validate_json(
        Path(os.getenv("SNAPSHOT_PATH", "datasets/snapshot.json")).read_text(encoding="utf-8")
    )


def select_dataset(fallback, engine):
    # Never switch to another dataset silently during a database outage.
    if engine is None:
        return fallback, "snapshot"
    with Session(engine) as session:
        row = session.scalar(select(Snapshot).where(Snapshot.version == fallback.version))
        if row is None:
            raise LookupError("Configured snapshot version is not seeded")
        candidate = Dataset.model_validate(row.payload)
        if candidate != fallback:
            raise ValueError("Database content differs from configured snapshot")
        return candidate, "postgresql"


def seed():
    dataset = read_snapshot()
    engine = engine_for(os.environ["DATABASE_URL"])
    with Session(engine) as session, session.begin():
        existing = session.get(Snapshot, dataset.version)
        payload = dataset.model_dump(mode="json")
        if existing and existing.payload != payload:
            raise ValueError("Immutable version already exists with different content")
        if existing is None:
            session.add(Snapshot(version=dataset.version, payload=payload))
    engine.dispose()
    print(f"Seeded {dataset.version}")


if __name__ == "__main__":
    seed()
