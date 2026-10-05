"""Local SQLite storage. Embeddings are encrypted before they are written."""

import sqlite3
from datetime import datetime, timezone

from . import config


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin'
            );

            CREATE TABLE IF NOT EXISTS zones (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS persons (
                id INTEGER PRIMARY KEY,
                research_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY,
                person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                embedding BLOB NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS person_zones (
                person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                zone_id INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
                PRIMARY KEY (person_id, zone_id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                zone_name TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                research_id TEXT,
                confidence REAL,
                elapsed_ms INTEGER NOT NULL,
                review_status TEXT NOT NULL,
                reviewed_at TEXT,
                review_note TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS n FROM zones").fetchone()["n"]
        if count == 0:
            conn.executemany(
                "INSERT INTO zones (name, description) VALUES (?, ?)",
                [
                    ("Main Entrance", "Controlled entry test zone"),
                    ("Laboratory", "Restricted laboratory test zone"),
                    ("Administrative Office", "Staff office test zone"),
                ],
            )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('email_enabled', '0')"
        )


def audit(actor, action, detail=""):
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (created_at, actor, action, detail) VALUES (?, ?, ?, ?)",
            (now_iso(), actor, action, detail[:500]),
        )


def get_setting(key, default=""):
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def user_by_name(username):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def create_user(username, password_hash, role="admin"):
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )


def list_zones():
    with connect() as conn:
        return conn.execute("SELECT * FROM zones ORDER BY name").fetchall()


def zone_by_id(zone_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()


def add_zone(name, description):
    with connect() as conn:
        conn.execute(
            "INSERT INTO zones (name, description) VALUES (?, ?)",
            (name.strip(), description.strip()),
        )


def list_persons():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.research_id, p.created_at,
                   COUNT(e.id) AS samples
            FROM persons p
            LEFT JOIN embeddings e ON e.person_id = p.id
            WHERE p.active = 1
            GROUP BY p.id
            ORDER BY p.research_id
            """
        ).fetchall()
        people = []
        for row in rows:
            zones = conn.execute(
                """
                SELECT z.name FROM zones z
                JOIN person_zones pz ON pz.zone_id = z.id
                WHERE pz.person_id = ?
                ORDER BY z.name
                """,
                (row["id"],),
            ).fetchall()
            people.append(
                {
                    "id": row["id"],
                    "research_id": row["research_id"],
                    "created_at": row["created_at"],
                    "samples": row["samples"],
                    "zones": [item["name"] for item in zones],
                }
            )
    return people


def person_by_research_id(research_id):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM persons WHERE research_id = ? AND active = 1",
            (research_id,),
        ).fetchone()


def enrollment_count(person_id):
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM embeddings WHERE person_id = ?",
            (person_id,),
        ).fetchone()["n"]


def create_person(research_id):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO persons (research_id, created_at) VALUES (?, ?)",
            (research_id, now_iso()),
        )
        return cur.lastrowid


def add_embedding(person_id, encrypted_blob):
    with connect() as conn:
        conn.execute(
            "INSERT INTO embeddings (person_id, embedding, created_at) VALUES (?, ?, ?)",
            (person_id, encrypted_blob, now_iso()),
        )


def set_person_zones(person_id, zone_ids):
    with connect() as conn:
        conn.execute("DELETE FROM person_zones WHERE person_id = ?", (person_id,))
        conn.executemany(
            "INSERT INTO person_zones (person_id, zone_id) VALUES (?, ?)",
            [(person_id, zone_id) for zone_id in zone_ids],
        )


def person_zone_ids(person_id):
    with connect() as conn:
        rows = conn.execute(
            "SELECT zone_id FROM person_zones WHERE person_id = ?",
            (person_id,),
        ).fetchall()
    return {row["zone_id"] for row in rows}


def all_embeddings():
    with connect() as conn:
        return conn.execute(
            """
            SELECT e.embedding, p.research_id, p.id AS person_id
            FROM embeddings e
            JOIN persons p ON p.id = e.person_id
            WHERE p.active = 1
            """
        ).fetchall()


def delete_person(person_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT research_id FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
    return row["research_id"] if row else None


def add_event(zone_name, decision, reason, research_id, confidence, elapsed_ms):
    needs_review = decision in ("unauthorized", "review_required")
    status = "open" if needs_review else "not_required"
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO events (
                created_at, zone_name, decision, reason, research_id,
                confidence, elapsed_ms, review_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                zone_name,
                decision,
                reason,
                research_id,
                confidence,
                elapsed_ms,
                status,
            ),
        )
        return cur.lastrowid


def recent_events(limit=8):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


def open_alerts():
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM events
            WHERE review_status = 'open'
            ORDER BY id DESC
            """
        ).fetchall()


def reviewed_alerts():
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM events
            WHERE review_status = 'reviewed'
            ORDER BY id DESC
            LIMIT 30
            """
        ).fetchall()


def review_event(event_id, note):
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE events
            SET review_status = 'reviewed', reviewed_at = ?, review_note = ?
            WHERE id = ? AND review_status = 'open'
            """,
            (now_iso(), note.strip()[:300], event_id),
        )
        return cur.rowcount == 1


def recent_audit(limit=100):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


def counts():
    with connect() as conn:
        people = conn.execute(
            "SELECT COUNT(*) AS n FROM persons WHERE active = 1"
        ).fetchone()["n"]
        open_count = conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE review_status = 'open'"
        ).fetchone()["n"]
        events = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    return {"people": people, "open_alerts": open_count, "events": events}


def last_event_time():
    with connect() as conn:
        row = conn.execute(
            "SELECT created_at FROM events ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return row["created_at"] if row else None
