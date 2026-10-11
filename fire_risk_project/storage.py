"""Evaluation storage adapters for SQLite and Postgres."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time


class StorageError(OSError):
    """Raised when the configured evaluation store is unavailable."""


def configured_storage(storage_path=None):
    if storage_path is not None:
        return storage_path
    return os.environ.get("DATABASE_URL") or Path(
        os.environ.get(
            "FIRE_RISK_STORAGE",
            Path(__file__).resolve().parent / "outputs/api_evaluations.sqlite3",
        )
    )


def is_postgres_storage(storage):
    return isinstance(storage, str) and storage.startswith(("postgres://", "postgresql://"))


def _connect_postgres(storage):
    try:
        import psycopg
    except ImportError as error:
        raise StorageError("Postgres 저장소를 사용하려면 psycopg가 필요합니다.") from error
    try:
        return psycopg.connect(storage)
    except Exception as error:
        raise StorageError("Postgres 저장소에 연결하지 못했습니다.") from error


def initialize(storage):
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evaluation_drafts (
                    evaluation_id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL
                )
            """)
        return

    target = Path(storage).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as conn, conn:
        conn.execute("CREATE TABLE IF NOT EXISTS evaluations (evaluation_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS evaluation_drafts (evaluation_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL)")


def save_draft(storage, record):
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False)
    created_at = time.time()
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            conn.execute("DELETE FROM evaluation_drafts WHERE created_at < %s", (created_at - 86400,))
            conn.execute("""
                INSERT INTO evaluation_drafts (evaluation_id, payload, created_at)
                VALUES (%s, %s::jsonb, %s)
                ON CONFLICT (evaluation_id) DO UPDATE
                SET payload = EXCLUDED.payload, created_at = EXCLUDED.created_at
            """, (record["평가ID"], payload, created_at))
        return

    with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn, conn:
        conn.execute("DELETE FROM evaluation_drafts WHERE created_at < ?", (created_at - 86400,))
        conn.execute("INSERT OR REPLACE INTO evaluation_drafts VALUES (?, ?, ?)",
                     (record["평가ID"], payload, created_at))


def saved_exists(storage, evaluation_id):
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            row = conn.execute(
                "SELECT 1 FROM evaluations WHERE evaluation_id = %s",
                (evaluation_id,),
            ).fetchone()
        return row is not None

    with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn:
        row = conn.execute(
            "SELECT 1 FROM evaluations WHERE evaluation_id = ?",
            (evaluation_id,),
        ).fetchone()
    return row is not None


def load_fresh_draft(storage, evaluation_id):
    cutoff = time.time() - 86400
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            row = conn.execute(
                "SELECT payload FROM evaluation_drafts WHERE evaluation_id = %s AND created_at >= %s",
                (evaluation_id, cutoff),
            ).fetchone()
        if row is None:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn:
        row = conn.execute(
            "SELECT payload FROM evaluation_drafts WHERE evaluation_id = ? AND created_at >= ?",
            (evaluation_id, cutoff),
        ).fetchone()
    return None if row is None else json.loads(row[0])
