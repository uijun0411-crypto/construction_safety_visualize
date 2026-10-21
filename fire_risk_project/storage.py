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
    database_url = os.environ.get("DATABASE_URL")
    if not database_url and (os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV")):
        raise StorageError(
            "Vercel functions have ephemeral storage. Configure DATABASE_URL with a persistent Postgres database."
        )
    return database_url or Path(
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS site_blueprint_images (
                    image_id TEXT PRIMARY KEY,
                    site_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    byte_size INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    image_data BYTEA NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS site_current_blueprints (
                    site_id TEXT PRIMARY KEY,
                    image_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS site_work_zones (
                    zone_id TEXT PRIMARY KEY,
                    site_id TEXT NOT NULL,
                    image_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    geometry_type TEXT NOT NULL,
                    coordinates TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS zone_assessment_drafts (
                    zone_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, image_id TEXT NOT NULL,
                    payload JSONB NOT NULL, updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS zone_assessments (
                    evaluation_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, image_id TEXT NOT NULL,
                    zone_id TEXT NOT NULL, payload JSONB NOT NULL, evaluated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS zone_assessments_lookup ON zone_assessments(site_id, image_id, zone_id, evaluated_at)")
        return

    target = Path(storage).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as conn, conn:
        conn.execute("CREATE TABLE IF NOT EXISTS evaluations (evaluation_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS evaluation_drafts (evaluation_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS site_blueprint_images (
                image_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, version INTEGER NOT NULL,
                filename TEXT NOT NULL, media_type TEXT NOT NULL, width INTEGER NOT NULL,
                height INTEGER NOT NULL, byte_size INTEGER NOT NULL, created_at TEXT NOT NULL,
                image_data BLOB NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS site_current_blueprints (
                site_id TEXT PRIMARY KEY, image_id TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS site_work_zones (
                zone_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, image_id TEXT NOT NULL,
                name TEXT NOT NULL, geometry_type TEXT NOT NULL, coordinates TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS zone_assessment_drafts (
                zone_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, image_id TEXT NOT NULL,
                payload TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS zone_assessments (
                evaluation_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, image_id TEXT NOT NULL,
                zone_id TEXT NOT NULL, payload TEXT NOT NULL, evaluated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS zone_assessments_lookup ON zone_assessments(site_id, image_id, zone_id, evaluated_at)")


def _blueprint_metadata(row):
    if row is None:
        return None
    keys = ("image_id", "site_id", "version", "filename", "media_type", "width", "height", "byte_size", "created_at")
    return dict(zip(keys, row[:len(keys)]))


def save_site_blueprint(storage, *, image_id, site_id, filename, media_type, width, height, image_data, created_at):
    byte_size = len(image_data)
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (site_id,))
            version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM site_blueprint_images WHERE site_id = %s", (site_id,)).fetchone()[0]
            conn.execute("""
                INSERT INTO site_blueprint_images
                (image_id, site_id, version, filename, media_type, width, height, byte_size, created_at, image_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (image_id, site_id, version, filename, media_type, width, height, byte_size, created_at, image_data))
            conn.execute("""
                INSERT INTO site_current_blueprints (site_id, image_id, updated_at) VALUES (%s, %s, %s)
                ON CONFLICT (site_id) DO UPDATE SET image_id = EXCLUDED.image_id, updated_at = EXCLUDED.updated_at
            """, (site_id, image_id, created_at))
            return {"image_id": image_id, "site_id": site_id, "version": version, "filename": filename,
                    "media_type": media_type, "width": width, "height": height, "byte_size": byte_size, "created_at": created_at}

    with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM site_blueprint_images WHERE site_id = ?", (site_id,)).fetchone()[0]
        conn.execute("""
            INSERT INTO site_blueprint_images
            (image_id, site_id, version, filename, media_type, width, height, byte_size, created_at, image_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (image_id, site_id, version, filename, media_type, width, height, byte_size, created_at, image_data))
        conn.execute("""
            INSERT INTO site_current_blueprints (site_id, image_id, updated_at) VALUES (?, ?, ?)
            ON CONFLICT (site_id) DO UPDATE SET image_id = excluded.image_id, updated_at = excluded.updated_at
        """, (site_id, image_id, created_at))
    return {"image_id": image_id, "site_id": site_id, "version": version, "filename": filename,
            "media_type": media_type, "width": width, "height": height, "byte_size": byte_size, "created_at": created_at}


def current_site_blueprint(storage, site_id):
    query = """
        SELECT i.image_id, i.site_id, i.version, i.filename, i.media_type, i.width, i.height,
               i.byte_size, i.created_at, i.image_data
        FROM site_current_blueprints c JOIN site_blueprint_images i ON i.image_id = c.image_id
        WHERE c.site_id = %s
    """ if is_postgres_storage(storage) else """
        SELECT i.image_id, i.site_id, i.version, i.filename, i.media_type, i.width, i.height,
               i.byte_size, i.created_at, i.image_data
        FROM site_current_blueprints c JOIN site_blueprint_images i ON i.image_id = c.image_id
        WHERE c.site_id = ?
    """
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            row = conn.execute(query, (site_id,)).fetchone()
    else:
        with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn:
            row = conn.execute(query, (site_id,)).fetchone()
    if row is None:
        return None
    data = bytes(row[9])
    return {**_blueprint_metadata(row), "image_data": data}


def site_blueprint(storage, site_id, image_id):
    query = """
        SELECT image_id, site_id, version, filename, media_type, width, height, byte_size, created_at, image_data
        FROM site_blueprint_images WHERE site_id = %s AND image_id = %s
    """ if is_postgres_storage(storage) else """
        SELECT image_id, site_id, version, filename, media_type, width, height, byte_size, created_at, image_data
        FROM site_blueprint_images WHERE site_id = ? AND image_id = ?
    """
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            row = conn.execute(query, (site_id, image_id)).fetchone()
    else:
        with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn:
            row = conn.execute(query, (site_id, image_id)).fetchone()
    if row is None:
        return None
    return {**_blueprint_metadata(row), "image_data": bytes(row[9])}


def site_blueprint_metadata(storage, site_id, image_id):
    query = """
        SELECT image_id, site_id, version, filename, media_type, width, height, byte_size, created_at
        FROM site_blueprint_images WHERE site_id = %s AND image_id = %s
    """ if is_postgres_storage(storage) else """
        SELECT image_id, site_id, version, filename, media_type, width, height, byte_size, created_at
        FROM site_blueprint_images WHERE site_id = ? AND image_id = ?
    """
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            row = conn.execute(query, (site_id, image_id)).fetchone()
    else:
        with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn:
            row = conn.execute(query, (site_id, image_id)).fetchone()
    return _blueprint_metadata(row)


def clear_current_site_blueprint(storage, site_id):
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            result = conn.execute("DELETE FROM site_current_blueprints WHERE site_id = %s", (site_id,))
            return result.rowcount > 0
    with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn, conn:
        result = conn.execute("DELETE FROM site_current_blueprints WHERE site_id = ?", (site_id,))
        return result.rowcount > 0


def _zone_record(row):
    if row is None:
        return None
    return {"zone_id": row[0], "site_id": row[1], "image_id": row[2], "name": row[3],
            "geometry_type": row[4], "coordinates": json.loads(row[5]),
            "created_at": row[6], "updated_at": row[7]}


def list_site_work_zones(storage, site_id, image_id):
    query = """
        SELECT zone_id, site_id, image_id, name, geometry_type, coordinates, created_at, updated_at
        FROM site_work_zones WHERE site_id = %s AND image_id = %s ORDER BY created_at, zone_id
    """ if is_postgres_storage(storage) else """
        SELECT zone_id, site_id, image_id, name, geometry_type, coordinates, created_at, updated_at
        FROM site_work_zones WHERE site_id = ? AND image_id = ? ORDER BY created_at, zone_id
    """
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            rows = conn.execute(query, (site_id, image_id)).fetchall()
    else:
        with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn:
            rows = conn.execute(query, (site_id, image_id)).fetchall()
    return [_zone_record(row) for row in rows]


def create_site_work_zone(storage, *, zone_id, site_id, image_id, name, geometry_type, coordinates, timestamp):
    serialized = json.dumps(coordinates, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            conn.execute("""
                INSERT INTO site_work_zones
                (zone_id, site_id, image_id, name, geometry_type, coordinates, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (zone_id, site_id, image_id, name, geometry_type, serialized, timestamp, timestamp))
    else:
        with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn, conn:
            conn.execute("""
                INSERT INTO site_work_zones
                (zone_id, site_id, image_id, name, geometry_type, coordinates, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (zone_id, site_id, image_id, name, geometry_type, serialized, timestamp, timestamp))
    return {"zone_id": zone_id, "site_id": site_id, "image_id": image_id, "name": name,
            "geometry_type": geometry_type, "coordinates": coordinates, "created_at": timestamp, "updated_at": timestamp}


def update_site_work_zone(storage, *, zone_id, site_id, image_id, name, coordinates, timestamp):
    serialized = json.dumps(coordinates, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    query = """
        UPDATE site_work_zones SET name = %s, coordinates = %s, updated_at = %s
        WHERE zone_id = %s AND site_id = %s AND image_id = %s
    """ if is_postgres_storage(storage) else """
        UPDATE site_work_zones SET name = ?, coordinates = ?, updated_at = ?
        WHERE zone_id = ? AND site_id = ? AND image_id = ?
    """
    params = (name, serialized, timestamp, zone_id, site_id, image_id)
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            result = conn.execute(query, params)
            return result.rowcount > 0
    with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn, conn:
        result = conn.execute(query, params)
        return result.rowcount > 0


def delete_site_work_zone(storage, zone_id, site_id, image_id):
    query = "DELETE FROM site_work_zones WHERE zone_id = %s AND site_id = %s AND image_id = %s" if is_postgres_storage(storage) else "DELETE FROM site_work_zones WHERE zone_id = ? AND site_id = ? AND image_id = ?"
    if is_postgres_storage(storage):
        with _connect_postgres(storage) as conn:
            result = conn.execute(query, (zone_id, site_id, image_id))
            return result.rowcount > 0
    with closing(sqlite3.connect(Path(storage).expanduser().resolve())) as conn, conn:
        result = conn.execute(query, (zone_id, site_id, image_id))
        return result.rowcount > 0


def site_work_zone(storage, site_id, image_id, zone_id):
    return next((zone for zone in list_site_work_zones(storage, site_id, image_id)
                 if zone["zone_id"] == zone_id), None)


def load_zone_draft(storage, site_id, image_id, zone_id):
    postgres = is_postgres_storage(storage)
    query = ("SELECT payload FROM zone_assessment_drafts WHERE site_id = %s AND image_id = %s AND zone_id = %s"
             if postgres else "SELECT payload FROM zone_assessment_drafts WHERE site_id = ? AND image_id = ? AND zone_id = ?")
    connection = _connect_postgres(storage) if postgres else sqlite3.connect(Path(storage).expanduser().resolve())
    with closing(connection) as conn:
        row = conn.execute(query, (site_id, image_id, zone_id)).fetchone()
    return None if row is None else row[0] if isinstance(row[0], dict) else json.loads(row[0])


def save_zone_draft(storage, site_id, image_id, zone_id, payload, updated_at):
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    postgres = is_postgres_storage(storage)
    query = """
        INSERT INTO zone_assessment_drafts(zone_id, site_id, image_id, payload, updated_at)
        VALUES (%s, %s, %s, %s::jsonb, %s)
        ON CONFLICT(zone_id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at
    """ if postgres else """
        INSERT INTO zone_assessment_drafts(zone_id, site_id, image_id, payload, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(zone_id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
    """
    connection = _connect_postgres(storage) if postgres else sqlite3.connect(Path(storage).expanduser().resolve())
    with closing(connection) as conn, conn:
        conn.execute(query, (zone_id, site_id, image_id, serialized, updated_at))


def latest_zone_assessment(storage, site_id, image_id, zone_id):
    postgres = is_postgres_storage(storage)
    query = ("SELECT payload FROM zone_assessments WHERE site_id = %s AND image_id = %s AND zone_id = %s ORDER BY evaluated_at DESC, evaluation_id DESC LIMIT 1"
             if postgres else "SELECT payload FROM zone_assessments WHERE site_id = ? AND image_id = ? AND zone_id = ? ORDER BY evaluated_at DESC, evaluation_id DESC LIMIT 1")
    connection = _connect_postgres(storage) if postgres else sqlite3.connect(Path(storage).expanduser().resolve())
    with closing(connection) as conn:
        row = conn.execute(query, (site_id, image_id, zone_id)).fetchone()
    return None if row is None else row[0] if isinstance(row[0], dict) else json.loads(row[0])


def list_zone_assessments(storage, site_id, image_id, zone_id):
    postgres = is_postgres_storage(storage)
    query = ("SELECT payload FROM zone_assessments WHERE site_id = %s AND image_id = %s AND zone_id = %s ORDER BY evaluated_at DESC, evaluation_id DESC"
             if postgres else "SELECT payload FROM zone_assessments WHERE site_id = ? AND image_id = ? AND zone_id = ? ORDER BY evaluated_at DESC, evaluation_id DESC")
    connection = _connect_postgres(storage) if postgres else sqlite3.connect(Path(storage).expanduser().resolve())
    with closing(connection) as conn:
        rows = conn.execute(query, (site_id, image_id, zone_id)).fetchall()
    return [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in rows]


def list_all_zone_assessments(storage, site_id=None):
    """Load the immutable zone records for the history index, newest first."""
    postgres = is_postgres_storage(storage)
    if site_id:
        query = ("SELECT payload FROM zone_assessments WHERE site_id = %s ORDER BY evaluated_at DESC, evaluation_id DESC"
                 if postgres else "SELECT payload FROM zone_assessments WHERE site_id = ? ORDER BY evaluated_at DESC, evaluation_id DESC")
        params = (site_id,)
    else:
        query = "SELECT payload FROM zone_assessments ORDER BY evaluated_at DESC, evaluation_id DESC"
        params = ()
    connection = _connect_postgres(storage) if postgres else sqlite3.connect(Path(storage).expanduser().resolve())
    with closing(connection) as conn:
        rows = conn.execute(query, params).fetchall()
    return [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in rows]


def zone_assessment_by_id(storage, evaluation_id):
    postgres = is_postgres_storage(storage)
    query = ("SELECT payload FROM zone_assessments WHERE evaluation_id = %s"
             if postgres else "SELECT payload FROM zone_assessments WHERE evaluation_id = ?")
    connection = _connect_postgres(storage) if postgres else sqlite3.connect(Path(storage).expanduser().resolve())
    with closing(connection) as conn:
        row = conn.execute(query, (evaluation_id,)).fetchone()
    return None if row is None else row[0] if isinstance(row[0], dict) else json.loads(row[0])


def save_zone_assessment(storage, site_id, image_id, zone_id, record):
    serialized = json.dumps(record, ensure_ascii=False, allow_nan=False)
    postgres = is_postgres_storage(storage)
    query = ("INSERT INTO zone_assessments(evaluation_id, site_id, image_id, zone_id, payload, evaluated_at) VALUES (%s, %s, %s, %s, %s::jsonb, %s)"
             if postgres else "INSERT INTO zone_assessments(evaluation_id, site_id, image_id, zone_id, payload, evaluated_at) VALUES (?, ?, ?, ?, ?, ?)")
    connection = _connect_postgres(storage) if postgres else sqlite3.connect(Path(storage).expanduser().resolve())
    with closing(connection) as conn, conn:
        conn.execute(query, (record["평가ID"], site_id, image_id, zone_id, serialized, record["평가일시"]))


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
