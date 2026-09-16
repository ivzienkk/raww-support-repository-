from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_CLAIM_A = (
    "¡Felicidades, {winner}! Has reclamado tu premio a tiempo. "
    "El staff se pondrá en contacto contigo."
)
DEFAULT_CLAIM_B = (
    "El tiempo para reclamar el premio terminó. El staff puede ejecutar un re-roll."
)
DEFAULT_FORBIDDEN_WORDS = ["scam.example", "phishing.example"]


class Database:
    """Small SQLite repository shared by the Discord bot and Flask thread."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    log_channel_id INTEGER,
                    claim_message_a TEXT NOT NULL,
                    claim_message_b TEXT NOT NULL,
                    forbidden_words TEXT NOT NULL,
                    allowed_nsfw_channels TEXT NOT NULL,
                    automod_enabled INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER,
                    creator_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    image_url TEXT,
                    description TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    winner_id INTEGER,
                    claim_expires_at TEXT,
                    claimed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    giveaway_id INTEGER NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (giveaway_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS warns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    removed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS mod_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    target_id INTEGER,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    user_id INTEGER,
                    channel_id INTEGER,
                    content TEXT,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def ensure_guild(self, guild_id: int) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO guild_settings
                    (guild_id, claim_message_a, claim_message_b, forbidden_words, allowed_nsfw_channels)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    DEFAULT_CLAIM_A,
                    DEFAULT_CLAIM_B,
                    json.dumps(DEFAULT_FORBIDDEN_WORDS),
                    json.dumps([]),
                ),
            )

    def get_settings(self, guild_id: int) -> dict[str, Any]:
        self.ensure_guild(guild_id)
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
            ).fetchone()
        result = dict(row)
        result["forbidden_words"] = json.loads(result["forbidden_words"])
        result["allowed_nsfw_channels"] = json.loads(result["allowed_nsfw_channels"])
        result["automod_enabled"] = bool(result["automod_enabled"])
        return result

    def update_settings(self, guild_id: int, **values: Any) -> None:
        self.ensure_guild(guild_id)
        allowed = {
            "log_channel_id",
            "claim_message_a",
            "claim_message_b",
            "forbidden_words",
            "allowed_nsfw_channels",
            "automod_enabled",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        if "forbidden_words" in updates:
            updates["forbidden_words"] = json.dumps(updates["forbidden_words"])
        if "allowed_nsfw_channels" in updates:
            updates["allowed_nsfw_channels"] = json.dumps(
                updates["allowed_nsfw_channels"]
            )
        if "automod_enabled" in updates:
            updates["automod_enabled"] = int(bool(updates["automod_enabled"]))
        columns = ", ".join(f"{key} = ?" for key in updates)
        with self.connection() as db:
            db.execute(
                f"UPDATE guild_settings SET {columns} WHERE guild_id = ?",
                (*updates.values(), guild_id),
            )

    def create_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        creator_id: int,
        title: str,
        image_url: str | None,
        description: str,
        ends_at: str,
        message_id: int | None = None,
    ) -> int:
        self.ensure_guild(guild_id)
        with self.connection() as db:
            cursor = db.execute(
                """
                INSERT INTO giveaways
                    (guild_id, channel_id, message_id, creator_id, title, image_url,
                     description, ends_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    channel_id,
                    message_id,
                    creator_id,
                    title,
                    image_url,
                    description,
                    ends_at,
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def set_giveaway_message(self, giveaway_id: int, message_id: int) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE giveaways SET message_id = ? WHERE id = ?",
                (message_id, giveaway_id),
            )

    def get_giveaway(self, giveaway_id: int) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM giveaways WHERE id = ?", (giveaway_id,)
            ).fetchone()
        return dict(row) if row else None

    def active_giveaways(self, guild_id: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM giveaways WHERE status = 'active'"
        args: tuple[Any, ...] = ()
        if guild_id is not None:
            query += " AND guild_id = ?"
            args = (guild_id,)
        query += " ORDER BY ends_at ASC"
        with self.connection() as db:
            return [dict(row) for row in db.execute(query, args).fetchall()]

    def claim_pending_giveaways(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT * FROM giveaways
                WHERE status = 'finished'
                  AND claimed = 0
                  AND claim_expires_at IS NOT NULL
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def join_giveaway(self, giveaway_id: int, user_id: int) -> bool:
        with self.connection() as db:
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO giveaway_entries (giveaway_id, user_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (giveaway_id, user_id, utc_now()),
            )
        return cursor.rowcount == 1

    def giveaway_entries(self, giveaway_id: int) -> list[int]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?",
                (giveaway_id,),
            ).fetchall()
        return [int(row["user_id"]) for row in rows]

    def finish_giveaway(
        self, giveaway_id: int, winner_id: int | None, claim_expires_at: str
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                UPDATE giveaways
                SET status = 'finished', winner_id = ?, claim_expires_at = ?
                WHERE id = ? AND status = 'active'
                """,
                (winner_id, claim_expires_at, giveaway_id),
            )

    def mark_claimed(self, giveaway_id: int) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE giveaways SET claimed = 1 WHERE id = ?", (giveaway_id,)
            )

    def add_warn(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        with self.connection() as db:
            cursor = db.execute(
                """
                INSERT INTO warns (guild_id, user_id, moderator_id, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, moderator_id, reason, utc_now()),
            )
            return int(cursor.lastrowid)

    def remove_warn(self, guild_id: int, warn_id: int) -> bool:
        with self.connection() as db:
            cursor = db.execute(
                """
                UPDATE warns SET active = 0, removed_at = ?
                WHERE id = ? AND guild_id = ? AND active = 1
                """,
                (utc_now(), warn_id, guild_id),
            )
        return cursor.rowcount == 1

    def get_warns(self, guild_id: int, user_id: int) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT * FROM warns
                WHERE guild_id = ? AND user_id = ? AND active = 1
                ORDER BY created_at DESC
                """,
                (guild_id, user_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_mod_action(
        self,
        guild_id: int,
        moderator_id: int,
        action_type: str,
        target_id: int | None,
        reason: str,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO mod_actions
                    (guild_id, moderator_id, action_type, target_id, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, moderator_id, action_type, target_id, reason, utc_now()),
            )

    def moderation_stats(self, guild_id: int) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT moderator_id,
                       SUM(action_type = 'ban') AS bans,
                       SUM(action_type = 'kick') AS kicks,
                       SUM(action_type = 'mute') AS mutes,
                       SUM(action_type = 'warn') AS warns,
                       COUNT(*) AS total
                FROM mod_actions
                WHERE guild_id = ?
                GROUP BY moderator_id
                ORDER BY total DESC
                """,
                (guild_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_audit_log(
        self,
        guild_id: int,
        event_type: str,
        user_id: int | None = None,
        channel_id: int | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO audit_logs
                    (guild_id, event_type, user_id, channel_id, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    event_type,
                    user_id,
                    channel_id,
                    content,
                    json.dumps(metadata or {}),
                    utc_now(),
                ),
            )

    def known_guilds(self) -> list[int]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT guild_id FROM guild_settings ORDER BY guild_id"
            ).fetchall()
        return [int(row["guild_id"]) for row in rows]
