"""Campaign knowledge ingestion and bounded retrieval.

The storage and embedding interfaces are deliberately provider-neutral. The first
vertical slice uses a dependency-free sparse lexical embedding in AVA's existing
SQLite database. A dense embedding/pgvector implementation can replace these two
interfaces without changing campaign, tool, or qualification code.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}", re.IGNORECASE)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EmbeddingProvider(ABC):
    """Replaceable embedding contract used by knowledge ingestion and search."""

    name = "abstract"

    @abstractmethod
    def embed(self, text: str) -> Dict[str, float]:
        """Return a JSON-serializable normalized sparse or dense vector."""

    @abstractmethod
    def similarity(self, left: Dict[str, float], right: Dict[str, float]) -> float:
        """Return a deterministic similarity score where larger is better."""


class SparseLexicalEmbeddingProvider(EmbeddingProvider):
    """Normalized term-frequency vectors suitable for a zero-dependency MVP."""

    name = "sparse_lexical_v1"

    def embed(self, text: str) -> Dict[str, float]:
        counts = Counter(token.casefold() for token in _TOKEN_RE.findall(text or ""))
        if not counts:
            return {}
        norm = math.sqrt(sum(float(value * value) for value in counts.values()))
        if norm <= 0:
            return {}
        return {token: count / norm for token, count in counts.items()}

    def similarity(self, left: Dict[str, float], right: Dict[str, float]) -> float:
        if not left or not right:
            return 0.0
        if len(left) > len(right):
            left, right = right, left
        return float(sum(value * right.get(token, 0.0) for token, value in left.items()))


def chunk_text(text: str, *, chunk_size: int = 1000, overlap: int = 150) -> List[str]:
    """Split text into bounded overlapping chunks without losing sentence context."""
    normalized = re.sub(r"\r\n?", "\n", str(text or "")).strip()
    if not normalized:
        return []
    size = max(200, min(4000, int(chunk_size)))
    shared = max(0, min(size // 2, int(overlap)))
    chunks: List[str] = []
    start = 0
    while start < len(normalized):
        hard_end = min(len(normalized), start + size)
        end = hard_end
        if hard_end < len(normalized):
            candidates = [
                normalized.rfind("\n\n", start + size // 2, hard_end),
                normalized.rfind(". ", start + size // 2, hard_end),
                normalized.rfind("\n", start + size // 2, hard_end),
                normalized.rfind(" ", start + size // 2, hard_end),
            ]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + (2 if normalized[boundary : boundary + 2] == ". " else 1)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        next_start = max(start + 1, end - shared)
        start = next_start
    return chunks


class KnowledgeBaseStore:
    _CREATE_SQL = (
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            name TEXT NOT NULL,
            content_type TEXT NOT NULL DEFAULT 'text/plain',
            content_sha256 TEXT NOT NULL,
            character_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(campaign_id, content_sha256)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_campaign ON knowledge_documents(campaign_id)",
        """
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding_provider TEXT NOT NULL,
            embedding_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            UNIQUE(document_id, chunk_index)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_campaign ON knowledge_chunks(campaign_id)",
        "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document ON knowledge_chunks(document_id)",
    )

    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        self._db_path = db_path or os.getenv("CALL_HISTORY_DB_PATH", "/app/data/call_history.db")
        self._enabled = str(os.getenv("CALL_HISTORY_ENABLED", "true")).strip().lower() not in {
            "0",
            "false",
            "no",
        }
        self._embedding_provider = embedding_provider or SparseLexicalEmbeddingProvider()
        self._lock = threading.Lock()
        if self._enabled:
            self._init_db()

    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def _init_db(self) -> None:
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._connection()
            try:
                for statement in self._CREATE_SQL:
                    conn.execute(statement)
                conn.commit()
            finally:
                conn.close()

    async def _run(self, fn):
        return await asyncio.get_event_loop().run_in_executor(None, fn)

    async def add_document(
        self,
        campaign_id: str,
        *,
        name: str,
        content: str,
        content_type: str = "text/plain",
    ) -> Dict[str, Any]:
        campaign = str(campaign_id or "").strip()
        document_name = str(name or "").strip() or "Untitled knowledge document"
        document_content = str(content or "").strip()
        if not campaign:
            raise ValueError("campaign_id is required")
        if not document_content:
            raise ValueError("knowledge document is empty")
        max_chars = int(os.getenv("AAVA_KNOWLEDGE_MAX_CHARACTERS", "2000000"))
        if len(document_content) > max(1, max_chars):
            raise ValueError(f"knowledge document exceeds {max_chars} characters")
        chunks = chunk_text(document_content)
        if not chunks:
            raise ValueError("knowledge document produced no searchable chunks")
        digest = hashlib.sha256(document_content.encode("utf-8")).hexdigest()

        def _sync() -> Dict[str, Any]:
            now = _utcnow_iso()
            document_id = str(uuid.uuid4())
            with self._lock:
                conn = self._connection()
                try:
                    existing = conn.execute(
                        "SELECT * FROM knowledge_documents WHERE campaign_id=? AND content_sha256=?",
                        (campaign, digest),
                    ).fetchone()
                    if existing:
                        return dict(existing)
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        """
                        INSERT INTO knowledge_documents (
                            id, campaign_id, name, content_type, content_sha256,
                            character_count, chunk_count, created_at_utc, updated_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            document_id,
                            campaign,
                            document_name,
                            str(content_type or "text/plain"),
                            digest,
                            len(document_content),
                            len(chunks),
                            now,
                            now,
                        ),
                    )
                    for index, chunk in enumerate(chunks):
                        vector = self._embedding_provider.embed(chunk)
                        conn.execute(
                            """
                            INSERT INTO knowledge_chunks (
                                id, campaign_id, document_id, chunk_index, content,
                                embedding_provider, embedding_json, created_at_utc
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                str(uuid.uuid4()),
                                campaign,
                                document_id,
                                index,
                                chunk,
                                self._embedding_provider.name,
                                json.dumps(vector, separators=(",", ":"), sort_keys=True),
                                now,
                            ),
                        )
                    conn.commit()
                    row = conn.execute(
                        "SELECT * FROM knowledge_documents WHERE id=?", (document_id,)
                    ).fetchone()
                    return dict(row)
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()

        return await self._run(_sync)

    async def list_documents(self, campaign_id: str) -> List[Dict[str, Any]]:
        campaign = str(campaign_id or "").strip()

        def _sync() -> List[Dict[str, Any]]:
            with self._lock:
                conn = self._connection()
                try:
                    rows = conn.execute(
                        """
                        SELECT * FROM knowledge_documents
                        WHERE campaign_id=? ORDER BY created_at_utc DESC
                        """,
                        (campaign,),
                    ).fetchall()
                    return [dict(row) for row in rows]
                finally:
                    conn.close()

        return await self._run(_sync)

    async def delete_document(self, campaign_id: str, document_id: str) -> bool:
        campaign = str(campaign_id or "").strip()
        document = str(document_id or "").strip()

        def _sync() -> bool:
            with self._lock:
                conn = self._connection()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        "DELETE FROM knowledge_chunks WHERE campaign_id=? AND document_id=?",
                        (campaign, document),
                    )
                    cursor = conn.execute(
                        "DELETE FROM knowledge_documents WHERE campaign_id=? AND id=?",
                        (campaign, document),
                    )
                    conn.commit()
                    return cursor.rowcount > 0
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()

        return await self._run(_sync)

    async def delete_campaign(self, campaign_id: str) -> None:
        campaign = str(campaign_id or "").strip()

        def _sync() -> None:
            with self._lock:
                conn = self._connection()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("DELETE FROM knowledge_chunks WHERE campaign_id=?", (campaign,))
                    conn.execute("DELETE FROM knowledge_documents WHERE campaign_id=?", (campaign,))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()

        await self._run(_sync)

    async def search(
        self,
        campaign_id: str,
        query: str,
        *,
        limit: int = 4,
        max_context_characters: int = 4000,
    ) -> List[Dict[str, Any]]:
        campaign = str(campaign_id or "").strip()
        clean_query = str(query or "").strip()
        if not campaign or not clean_query:
            return []
        query_vector = self._embedding_provider.embed(clean_query)
        if not query_vector:
            return []
        bounded_limit = max(1, min(10, int(limit or 4)))
        max_chars = max(200, min(12000, int(max_context_characters or 4000)))

        def _sync() -> List[Dict[str, Any]]:
            with self._lock:
                conn = self._connection()
                try:
                    rows = conn.execute(
                        """
                        SELECT c.id, c.document_id, c.chunk_index, c.content,
                               c.embedding_provider, c.embedding_json, d.name AS document_name
                        FROM knowledge_chunks c
                        JOIN knowledge_documents d ON d.id = c.document_id
                        WHERE c.campaign_id=?
                        """,
                        (campaign,),
                    ).fetchall()
                finally:
                    conn.close()
            ranked: List[Dict[str, Any]] = []
            for row in rows:
                if str(row["embedding_provider"] or "") != self._embedding_provider.name:
                    continue
                try:
                    vector = json.loads(str(row["embedding_json"] or "{}"))
                except (TypeError, ValueError):
                    continue
                score = self._embedding_provider.similarity(query_vector, vector)
                if score <= 0:
                    continue
                ranked.append(
                    {
                        "chunk_id": str(row["id"]),
                        "document_id": str(row["document_id"]),
                        "document_name": str(row["document_name"]),
                        "chunk_index": int(row["chunk_index"]),
                        "content": str(row["content"]),
                        "score": round(float(score), 6),
                    }
                )
            ranked.sort(key=lambda item: (-item["score"], item["document_id"], item["chunk_index"]))
            selected: List[Dict[str, Any]] = []
            used = 0
            for item in ranked[:bounded_limit]:
                remaining = max_chars - used
                if remaining <= 0:
                    break
                content = item["content"][:remaining]
                selected.append({**item, "content": content})
                used += len(content)
            return selected

        return await self._run(_sync)


_knowledge_store: Optional[KnowledgeBaseStore] = None


def get_knowledge_base_store() -> KnowledgeBaseStore:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = KnowledgeBaseStore()
    return _knowledge_store
