import os
import time

import aiosqlite

from bot.config import DATABASE_PATH, DEFAULT_API_KEY, DEFAULT_API_URL, DEFAULT_MODEL, DEFAULT_PROMPT

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    business_id    TEXT    DEFAULT '',
    prompt         TEXT    DEFAULT '',
    api_key        TEXT    DEFAULT '',
    api_url        TEXT    DEFAULT '',
    model          TEXT    DEFAULT '',
    is_connected   INTEGER DEFAULT 0,
    auto_reply     INTEGER DEFAULT 1,
    created_at     REAL    DEFAULT 0
);

CREATE TABLE IF NOT EXISTS monitored_chats (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    chat_id    INTEGER NOT NULL,
    chat_name  TEXT    DEFAULT '',
    auto_reply INTEGER DEFAULT 1,
    reading    INTEGER DEFAULT 1,
    UNIQUE(user_id, chat_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    chat_id   INTEGER NOT NULL,
    role      TEXT    NOT NULL,
    content   TEXT    NOT NULL,
    ts        REAL    DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_user_chat ON messages(user_id, chat_id, ts);

CREATE TABLE IF NOT EXISTS chat_content (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    chat_id      INTEGER NOT NULL,
    sender_id    INTEGER DEFAULT 0,
    sender_name  TEXT    DEFAULT '',
    content_type TEXT    NOT NULL,
    text_content TEXT    DEFAULT '',
    file_id      TEXT    DEFAULT '',
    caption      TEXT    DEFAULT '',
    emoji        TEXT    DEFAULT '',
    ts           REAL    DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_content_user_chat ON chat_content(user_id, chat_id, ts);
CREATE INDEX IF NOT EXISTS idx_content_type ON chat_content(user_id, content_type);

CREATE TABLE IF NOT EXISTS chat_knowledge (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    chat_id   INTEGER NOT NULL,
    topic     TEXT    DEFAULT '',
    summary   TEXT    DEFAULT '',
    words     TEXT    DEFAULT '',
    ts        REAL    DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""


class Database:
    def __init__(self) -> None:
        self._path = DATABASE_PATH
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not initialised"
        return self._db

    # ── users ──────────────────────────────────────────────────────

    async def get_user(self, user_id: int) -> dict | None:
        cur = await self.db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def upsert_user(self, user_id: int, **kwargs: object) -> None:
        existing = await self.get_user(user_id)
        if existing is None:
            api_key = DEFAULT_API_KEY
            await self.db.execute(
                "INSERT INTO users (user_id, prompt, api_key, api_url, model, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, DEFAULT_PROMPT, api_key, DEFAULT_API_URL, DEFAULT_MODEL, time.time()),
            )
        if kwargs:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            vals = list(kwargs.values()) + [user_id]
            await self.db.execute(f"UPDATE users SET {sets} WHERE user_id = ?", vals)  # noqa: S608
        await self.db.commit()

    async def set_user_field(self, user_id: int, field: str, value: object) -> None:
        await self.upsert_user(user_id, **{field: value})

    async def get_user_field(self, user_id: int, field: str, default: object = "") -> object:
        user = await self.get_user(user_id)
        if user is None:
            return default
        return user.get(field, default)

    # ── business connection ────────────────────────────────────────

    async def set_business_connected(
        self, user_id: int, business_id: str, connected: bool
    ) -> None:
        await self.upsert_user(
            user_id,
            business_id=business_id,
            is_connected=int(connected),
        )

    # ── monitored chats ────────────────────────────────────────────

    async def add_monitored_chat(
        self, user_id: int, chat_id: int, chat_name: str = ""
    ) -> bool:
        try:
            await self.db.execute(
                "INSERT OR IGNORE INTO monitored_chats (user_id, chat_id, chat_name) "
                "VALUES (?, ?, ?)",
                (user_id, chat_id, chat_name),
            )
            await self.db.commit()
            return True
        except Exception:
            return False

    async def remove_monitored_chat(self, user_id: int, chat_id: int) -> None:
        await self.db.execute(
            "DELETE FROM monitored_chats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        await self.db.commit()

    async def get_monitored_chats(self, user_id: int) -> list[dict]:
        cur = await self.db.execute(
            "SELECT * FROM monitored_chats WHERE user_id = ?", (user_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def is_chat_monitored(self, user_id: int, chat_id: int) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM monitored_chats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        return await cur.fetchone() is not None

    async def toggle_chat_auto_reply(self, user_id: int, chat_id: int) -> bool:
        cur = await self.db.execute(
            "SELECT auto_reply FROM monitored_chats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        if row is None:
            return False
        new_val = 0 if row["auto_reply"] else 1
        await self.db.execute(
            "UPDATE monitored_chats SET auto_reply = ? WHERE user_id = ? AND chat_id = ?",
            (new_val, user_id, chat_id),
        )
        await self.db.commit()
        return bool(new_val)

    # ── messages / history ─────────────────────────────────────────

    async def save_message(
        self, user_id: int, chat_id: int, role: str, content: str
    ) -> None:
        await self.db.execute(
            "INSERT INTO messages (user_id, chat_id, role, content, ts) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, role, content, time.time()),
        )
        await self.db.commit()

    async def get_history(
        self, user_id: int, chat_id: int, limit: int = 50
    ) -> list[dict]:
        cur = await self.db.execute(
            "SELECT role, content, ts FROM messages "
            "WHERE user_id = ? AND chat_id = ? ORDER BY ts DESC LIMIT ?",
            (user_id, chat_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def get_recent_chats(self, user_id: int, limit: int = 20) -> list[dict]:
        cur = await self.db.execute(
            "SELECT chat_id, MAX(content) as last_msg, MAX(ts) as last_ts, COUNT(*) as msg_count "
            "FROM messages WHERE user_id = ? GROUP BY chat_id ORDER BY last_ts DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def clear_history(self, user_id: int, chat_id: int | None = None) -> int:
        if chat_id is not None:
            cur = await self.db.execute(
                "DELETE FROM messages WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id),
            )
        else:
            cur = await self.db.execute(
                "DELETE FROM messages WHERE user_id = ?", (user_id,)
            )
        await self.db.commit()
        return cur.rowcount

    # ── chat content (all types) ───────────────────────────────────

    async def save_content(
        self,
        user_id: int,
        chat_id: int,
        sender_id: int,
        sender_name: str,
        content_type: str,
        text_content: str = "",
        file_id: str = "",
        caption: str = "",
        emoji: str = "",
    ) -> None:
        await self.db.execute(
            "INSERT INTO chat_content "
            "(user_id, chat_id, sender_id, sender_name, content_type, "
            "text_content, file_id, caption, emoji, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, sender_id, sender_name, content_type,
             text_content, file_id, caption, emoji, time.time()),
        )
        await self.db.commit()

    async def get_chat_content_stats(self, user_id: int, chat_id: int) -> dict:
        stats: dict = {}
        cur = await self.db.execute(
            "SELECT content_type, COUNT(*) as cnt FROM chat_content "
            "WHERE user_id = ? AND chat_id = ? GROUP BY content_type",
            (user_id, chat_id),
        )
        rows = await cur.fetchall()
        for r in rows:
            stats[r["content_type"]] = r["cnt"]

        cur2 = await self.db.execute(
            "SELECT COUNT(*) as total FROM chat_content WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        row = await cur2.fetchone()
        stats["total"] = row["total"] if row else 0
        return stats

    async def get_chat_words(self, user_id: int, chat_id: int, limit: int = 200) -> list[str]:
        cur = await self.db.execute(
            "SELECT text_content FROM chat_content "
            "WHERE user_id = ? AND chat_id = ? AND content_type = 'text' "
            "ORDER BY ts DESC LIMIT ?",
            (user_id, chat_id, limit),
        )
        rows = await cur.fetchall()
        return [r["text_content"] for r in rows if r["text_content"]]

    async def get_all_content_stats(self, user_id: int) -> dict:
        cur = await self.db.execute(
            "SELECT COUNT(*) as total FROM chat_content WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        total = row["total"] if row else 0

        cur2 = await self.db.execute(
            "SELECT content_type, COUNT(*) as cnt FROM chat_content "
            "WHERE user_id = ? GROUP BY content_type",
            (user_id,),
        )
        rows = await cur2.fetchall()
        by_type = {r["content_type"]: r["cnt"] for r in rows}

        cur3 = await self.db.execute(
            "SELECT COUNT(DISTINCT chat_id) as chats FROM chat_content WHERE user_id = ?",
            (user_id,),
        )
        row3 = await cur3.fetchone()
        chats = row3["chats"] if row3 else 0

        return {"total": total, "by_type": by_type, "chats": chats}

    async def get_recent_texts_for_learning(
        self, user_id: int, chat_id: int | None = None, limit: int = 100
    ) -> list[dict]:
        if chat_id:
            cur = await self.db.execute(
                "SELECT sender_name, text_content, ts FROM chat_content "
                "WHERE user_id = ? AND chat_id = ? AND text_content != '' "
                "ORDER BY ts DESC LIMIT ?",
                (user_id, chat_id, limit),
            )
        else:
            cur = await self.db.execute(
                "SELECT sender_name, text_content, ts FROM chat_content "
                "WHERE user_id = ? AND text_content != '' "
                "ORDER BY ts DESC LIMIT ?",
                (user_id, limit),
            )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    # ── knowledge ──────────────────────────────────────────────────

    async def save_knowledge(
        self, user_id: int, chat_id: int, topic: str, summary: str, words: str
    ) -> None:
        await self.db.execute(
            "INSERT INTO chat_knowledge (user_id, chat_id, topic, summary, words, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, topic, summary, words, time.time()),
        )
        await self.db.commit()

    async def get_knowledge(self, user_id: int, chat_id: int | None = None) -> list[dict]:
        if chat_id:
            cur = await self.db.execute(
                "SELECT * FROM chat_knowledge WHERE user_id = ? AND chat_id = ? ORDER BY ts DESC",
                (user_id, chat_id),
            )
        else:
            cur = await self.db.execute(
                "SELECT * FROM chat_knowledge WHERE user_id = ? ORDER BY ts DESC",
                (user_id,),
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
