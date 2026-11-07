from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
import httpx

from amadeus.config import AmadeusSettings, get_default_data_dir


@dataclass(slots=True)
class MemoryRecord:
    user_id: str
    user_message: str
    assistant_message: str
    extracted_fact: str
    timestamp: str


class LocalSQLiteMemory:
    """
    Ultra-lightweight local memory backend using SQLite + FTS5 full-text search.
    Consumes virtually zero idle RAM and works 100% offline with zero external servers.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        target_dir = get_default_data_dir()
        self.db_path = db_path or (target_dir / "amadeus_memory.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    assistant_message TEXT NOT NULL,
                    extracted_fact TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts USING fts5(
                    user_id UNINDEXED,
                    user_message,
                    assistant_message,
                    extracted_fact,
                    content='interactions',
                    content_rowid='id'
                );
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS interactions_ai AFTER INSERT ON interactions BEGIN
                    INSERT INTO interactions_fts(rowid, user_id, user_message, assistant_message, extracted_fact)
                    VALUES (new.id, new.user_id, new.user_message, new.assistant_message, new.extracted_fact);
                END;
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    emotion TEXT DEFAULT 'neutral',
                    metadata_json TEXT DEFAULT '{}',
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);
                """
            )

    @staticmethod
    def extract_heuristic_fact(user_msg: str) -> str:
        """Lightweight zero-LLM heuristic extraction of user preferences/habits."""
        patterns = [
            r"(?:me gusta|prefiero|suelo|mi horario es|trabajo en|estudio|odio|mi nombre es|llámame)\s+(.+)",
            r"(?:recuerda que|no olvides que|ten en cuenta que)\s+(.+)",
        ]
        for pat in patterns:
            match = re.search(pat, user_msg, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return ""

    def store(self, user_id: str, user_msg: str, assistant_msg: str) -> MemoryRecord:
        fact = self.extract_heuristic_fact(user_msg)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO interactions (user_id, user_message, assistant_message, extracted_fact, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, user_msg, assistant_msg, fact, now),
            )
        return MemoryRecord(
            user_id=user_id,
            user_message=user_msg,
            assistant_message=assistant_msg,
            extracted_fact=fact,
            timestamp=now,
        )

    async def retrieve_context(self, user_id: str, query: str) -> str:
        records = self.search(user_id, query, limit=4)
        if not records:
            return ""
        formatted = []
        for rec in records:
            if rec.extracted_fact:
                formatted.append(f"• Hecho recordado: {rec.extracted_fact}")
            else:
                formatted.append(
                    f"• Conversación previa: Usuario='{rec.user_message}' -> Kurisu='{rec.assistant_message}'"
                )
        return "[Memoria Local SQLite FTS5]:\n" + "\n".join(formatted)

    async def record_interaction(
        self, user_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        self.store(user_id, user_msg, assistant_msg)

    def search(self, user_id: str, query: str, limit: int = 5) -> List[MemoryRecord]:
        # Sanitize FTS5 query tokens
        tokens = [
            re.sub(r"[^\wáéíóúñÁÉÍÓÚÑ]", "", w)
            for w in query.split()
            if len(w) >= 3
        ]
        tokens = [t for t in tokens if t]
        with self._connect() as conn:
            if tokens:
                fts_query = " OR ".join(f'"{t}"' for t in tokens[:6])
                rows = conn.execute(
                    """
                    SELECT i.user_id, i.user_message, i.assistant_message, i.extracted_fact, i.timestamp
                    FROM interactions_fts f
                    JOIN interactions i ON f.rowid = i.id
                    WHERE i.user_id = ? AND interactions_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (user_id, fts_query, limit),
                ).fetchall()
                if rows:
                    return [MemoryRecord(*r) for r in rows]

            # Fallback to recent extracted facts if FTS query had no keyword match
            rows = conn.execute(
                """
                SELECT user_id, user_message, assistant_message, extracted_fact, timestamp
                FROM interactions
                WHERE user_id = ? AND extracted_fact != ''
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [MemoryRecord(*r) for r in rows]

    # --- Persistent Chat Sessions & Message History ---

    def get_or_create_active_session(self) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM chat_sessions ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if row:
                return str(row[0])
            sess_id = uuid.uuid4().hex[:12]
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO chat_sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (sess_id, "Conversación Principal", now, now),
            )
            return sess_id

    def create_new_session(self, title: Optional[str] = None) -> str:
        sess_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        t = title or f"Conversación {now[:10]} {now[11:16]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chat_sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (sess_id, t, now, now),
            )
        return sess_id

    def save_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        emotion: str = "neutral",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, emotion, metadata_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, role, content, emotion, meta_str, now),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )

    def load_recent_messages(
        self, session_id: Optional[str] = None, limit: int = 16
    ) -> List[Dict[str, Any]]:
        sid = session_id or self.get_or_create_active_session()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, emotion, metadata_json, timestamp
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (sid, limit),
            ).fetchall()
            messages = []
            for r in reversed(rows):
                try:
                    meta = json.loads(r[3])
                except Exception:
                    meta = {}
                messages.append(
                    {
                        "role": r[0],
                        "content": r[1],
                        "emotion": r[2],
                        "metadata": meta,
                        "timestamp": r[4],
                    }
                )
            return messages

    def list_chat_sessions(self, limit: int = 12) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.session_id, s.title, s.created_at, s.updated_at,
                       (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.session_id) as msg_count
                FROM chat_sessions s
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {
                    "session_id": r[0],
                    "title": r[1],
                    "created_at": r[2],
                    "updated_at": r[3],
                    "msg_count": r[4],
                }
                for r in rows
            ]

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            res = conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            return res.rowcount > 0


class HonchoCloudAdapter:
    """
    Plastic Labs Honcho Cloud API connector for cross-session dialectic user modeling.
    Zero local database overhead — runs entirely over lightweight REST requests.
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings
        self._external_client = http_client is not None
        self._client = http_client

    @property
    def is_enabled(self) -> bool:
        return bool(self.settings.use_honcho_cloud and self.settings.honcho_api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._external_client and not self._client.is_closed:
            await self._client.aclose()

    async def query_dialectic_representation(self, user_id: str, query: str) -> str:
        """Query Honcho's dialectic endpoint to get evolving psychological/preference context."""
        if not self.is_enabled:
            return ""
        client = await self._get_client()
        url = f"{self.settings.honcho_base_url.rstrip('/')}/apps/{self.settings.honcho_app_id}/users/{user_id}/chat"
        headers = {"Authorization": f"Bearer {self.settings.honcho_api_key}"}
        resp = await client.post(url, headers=headers, json={"query": query})
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("content") or data.get("representation") or "").strip()

    async def record_turn(
        self, user_id: str, user_msg: str, assistant_msg: str
    ) -> bool:
        """Send conversation turn to Honcho Cloud for background dialectic observation."""
        if not self.is_enabled:
            return False
        client = await self._get_client()
        url = f"{self.settings.honcho_base_url.rstrip('/')}/apps/{self.settings.honcho_app_id}/users/{user_id}/messages"
        headers = {"Authorization": f"Bearer {self.settings.honcho_api_key}"}
        payload = {
            "messages": [
                {"is_user": True, "content": user_msg},
                {"is_user": False, "content": assistant_msg},
            ]
        }
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return True


class HybridMemoryManager:
    """
    Module 5 (Memoria Híbrida):
    Combines Honcho Cloud dialectic reasoning with LocalSQLiteMemory (FTS5).
    Guarantees 100% availability even offline or without a Honcho API key.
    """

    def __init__(
        self,
        settings: AmadeusSettings,
        db_path: Optional[Path] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.local = LocalSQLiteMemory(db_path=db_path)
        self.honcho = HonchoCloudAdapter(settings=settings, http_client=http_client)

    async def retrieve_context(self, user_id: str, query: str) -> str:
        parts: List[str] = []

        # 1. Try Honcho Cloud dialectic user modeling if configured
        if self.honcho.is_enabled:
            try:
                dialectic = await self.honcho.query_dialectic_representation(
                    user_id, query
                )
                if dialectic:
                    parts.append(f"[Honcho Dialectic Profile]: {dialectic}")
            except Exception:
                # Graceful degradation to local SQLite per ECC rules
                pass

        # 2. Always enrich with fast local SQLite FTS5 matches
        records = self.local.search(user_id, query, limit=4)
        if records:
            formatted = []
            for rec in records:
                if rec.extracted_fact:
                    formatted.append(f"• Hecho recordado: {rec.extracted_fact}")
                else:
                    formatted.append(
                        f"• Conversación previa: Usuario='{rec.user_message}' -> Kurisu='{rec.assistant_message}'"
                    )
            parts.append("[Memoria Local SQLite FTS5]:\n" + "\n".join(formatted))

        return "\n\n".join(parts)

    async def record_interaction(
        self, user_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        self.local.store(user_id, user_msg, assistant_msg)
        if self.honcho.is_enabled:
            try:
                await self.honcho.record_turn(user_id, user_msg, assistant_msg)
            except Exception:
                pass

    def get_or_create_active_session(self) -> str:
        return self.local.get_or_create_active_session()

    def create_new_session(self, title: Optional[str] = None) -> str:
        return self.local.create_new_session(title=title)

    def save_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        emotion: str = "neutral",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.local.save_chat_message(
            session_id, role, content, emotion=emotion, metadata=metadata
        )

    def load_recent_messages(
        self, session_id: Optional[str] = None, limit: int = 16
    ) -> List[Dict[str, Any]]:
        return self.local.load_recent_messages(session_id=session_id, limit=limit)

    def list_chat_sessions(self, limit: int = 12) -> List[Dict[str, Any]]:
        return self.local.list_chat_sessions(limit=limit)

    def delete_session(self, session_id: str) -> bool:
        return self.local.delete_session(session_id)
