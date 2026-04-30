"""
utils/db.py — SQLite helpers for New Year Train bot (multi-guild).

Schema:
  train_stops         — static stop definitions (global, seeded once)
  scheduled_jobs      — per-year computed UTC fire times (global, year-keyed)
  guild_config        — per-guild settings (channel_id, enabled)
  guild_stop_enabled  — per-guild per-stop enable/disable overrides
                        (absent row = enabled by default)
  delivery_log        — per-guild per-job sent tracking
"""

import sqlite3
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", "data/new_year_train.db"))


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS train_stops (
            stop_number     INTEGER PRIMARY KEY,
            utc_offset_mins INTEGER NOT NULL,
            stop_label      TEXT    NOT NULL,
            clock_emoji     TEXT    NOT NULL,
            locations_text  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            year        INTEGER NOT NULL,
            job_type    TEXT    NOT NULL,
            stop_number INTEGER,
            fire_utc    TEXT    NOT NULL,
            UNIQUE (year, job_type)
        );

        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id    TEXT PRIMARY KEY,
            channel_id  TEXT,
            enabled     INTEGER NOT NULL DEFAULT 0,
            added_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS guild_stop_enabled (
            guild_id    TEXT    NOT NULL,
            stop_key    TEXT    NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (guild_id, stop_key),
            FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS delivery_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id    TEXT    NOT NULL,
            job_id      INTEGER NOT NULL,
            sent_at     TEXT    NOT NULL,
            UNIQUE (guild_id, job_id)
        );
        """)
    print("[db] Database initialised.")


# ---------------------------------------------------------------------------
# train_stops + scheduled_jobs (global)
# ---------------------------------------------------------------------------

def get_stop(stop_number: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM train_stops WHERE stop_number = ?", (stop_number,)
        ).fetchone()


def get_all_stops() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM train_stops ORDER BY stop_number"
        ).fetchall()


def upsert_scheduled_job(year: int, job_type: str, fire_utc: str, stop_number: int | None = None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO scheduled_jobs (year, job_type, stop_number, fire_utc)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(year, job_type) DO UPDATE SET
                   fire_utc    = excluded.fire_utc,
                   stop_number = excluded.stop_number""",
            (year, job_type, stop_number, fire_utc)
        )


def jobs_exist_for_year(year: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM scheduled_jobs WHERE year = ?", (year,)
        ).fetchone()
    return row["cnt"] > 0


def bookends_exist_for_year(year: int) -> bool:
    """Return True only if both pre_train and post_train jobs exist for year."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM scheduled_jobs
               WHERE year = ? AND job_type IN ('pre_train', 'post_train')""",
            (year,)
        ).fetchone()
    return row["cnt"] == 2


def get_all_jobs_for_year(year: int) -> list[sqlite3.Row]:
    """All jobs for a year joined with stop data, ordered by fire time."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT sj.*, ts.locations_text, ts.stop_label, ts.clock_emoji, ts.utc_offset_mins
               FROM scheduled_jobs sj
               LEFT JOIN train_stops ts ON sj.stop_number = ts.stop_number
               WHERE sj.year = ?
               ORDER BY sj.fire_utc""",
            (year,)
        ).fetchall()


# ---------------------------------------------------------------------------
# Guild config
# ---------------------------------------------------------------------------

def ensure_guild(guild_id: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
            (str(guild_id),)
        )


def get_guild_config(guild_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (str(guild_id),)
        ).fetchone()


def set_guild_channel(guild_id: int, channel_id: int):
    ensure_guild(guild_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE guild_config SET channel_id = ? WHERE guild_id = ?",
            (str(channel_id), str(guild_id))
        )


def set_guild_enabled(guild_id: int, enabled: bool):
    ensure_guild(guild_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE guild_config SET enabled = ? WHERE guild_id = ?",
            (1 if enabled else 0, str(guild_id))
        )


def get_all_active_guilds() -> list[sqlite3.Row]:
    """All guilds that are enabled and have a channel configured."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM guild_config WHERE enabled = 1 AND channel_id IS NOT NULL"
        ).fetchall()


def get_all_guilds() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM guild_config ORDER BY added_at").fetchall()


# ---------------------------------------------------------------------------
# Per-guild stop overrides
# ---------------------------------------------------------------------------

def set_stop_enabled(guild_id: int, stop_key: str, enabled: bool):
    """stop_key: 'pre_train', 'stop_1'..'stop_38', 'post_train'"""
    ensure_guild(guild_id)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO guild_stop_enabled (guild_id, stop_key, enabled)
               VALUES (?, ?, ?)
               ON CONFLICT(guild_id, stop_key) DO UPDATE SET enabled = excluded.enabled""",
            (str(guild_id), stop_key, 1 if enabled else 0)
        )


def set_stop_range_enabled(guild_id: int, start: int, end: int, enabled: bool):
    """Enable/disable stop_N through stop_M inclusive."""
    ensure_guild(guild_id)
    with get_conn() as conn:
        for n in range(start, end + 1):
            conn.execute(
                """INSERT INTO guild_stop_enabled (guild_id, stop_key, enabled)
                   VALUES (?, ?, ?)
                   ON CONFLICT(guild_id, stop_key) DO UPDATE SET enabled = excluded.enabled""",
                (str(guild_id), f"stop_{n}", 1 if enabled else 0)
            )


def is_stop_enabled(guild_id: int, stop_key: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT enabled FROM guild_stop_enabled WHERE guild_id = ? AND stop_key = ?",
            (str(guild_id), stop_key)
        ).fetchone()
    return bool(row["enabled"]) if row else True  # absent row = enabled


def get_disabled_stops(guild_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT stop_key FROM guild_stop_enabled WHERE guild_id = ? AND enabled = 0 ORDER BY stop_key",
            (str(guild_id),)
        ).fetchall()
    return [r["stop_key"] for r in rows]


def reset_stop_overrides(guild_id: int):
    """Re-enable all stops for a guild by clearing all override rows."""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM guild_stop_enabled WHERE guild_id = ?", (str(guild_id),)
        )


# ---------------------------------------------------------------------------
# Delivery log (per-guild per-job tracking)
# ---------------------------------------------------------------------------

def has_delivered(guild_id: int, job_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM delivery_log WHERE guild_id = ? AND job_id = ?",
            (str(guild_id), job_id)
        ).fetchone()
    return row is not None


def mark_delivered(guild_id: int, job_id: int, sent_at: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO delivery_log (guild_id, job_id, sent_at) VALUES (?, ?, ?)",
            (str(guild_id), job_id, sent_at)
        )


def count_delivered(guild_id: int, year: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM delivery_log dl
               JOIN scheduled_jobs sj ON dl.job_id = sj.id
               WHERE dl.guild_id = ? AND sj.year = ?""",
            (str(guild_id), year)
        ).fetchone()
    return row["cnt"] if row else 0


def reset_delivery_log(guild_id: int, year: int):
    """Clear sent history for a guild+year (for testing)."""
    with get_conn() as conn:
        conn.execute(
            """DELETE FROM delivery_log WHERE guild_id = ?
               AND job_id IN (SELECT id FROM scheduled_jobs WHERE year = ?)""",
            (str(guild_id), year)
        )