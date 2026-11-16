# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

"""A small SQLite-backed inverted index for exact winnowing fingerprints."""

from pathlib import Path
import sqlite3
from contextlib import contextmanager
from typing import Iterator
from typing import Protocol

from .normalize import normalize_text
from .winnowing import DEFAULT_K, DEFAULT_W, Fingerprint, fingerprint_text


class FingerprintIndex(Protocol):
    def add_document(self, source_id: str, title: str, text: str, *, source_url: str = "",
                     license_name: str = "") -> None: ...

    def document_count(self) -> int: ...


class SQLiteFingerprintIndex:
    """SQLite inverted index; the database may be rebuilt from its corpus."""

    def __init__(self, database: str | Path, *, k: int = DEFAULT_K, w: int = DEFAULT_W):
        if k < 1 or w < 1:
            raise ValueError("k and w must be at least 1")
        self.database = str(database)
        self.k = k
        self.w = w
        if self.database != ":memory:":
            Path(self.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS reference_documents (
                    source_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    license_name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fingerprints (
                    source_id TEXT NOT NULL REFERENCES reference_documents(source_id) ON DELETE CASCADE,
                    token_position INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    shingle TEXT NOT NULL,
                    char_start INTEGER NOT NULL,
                    char_end INTEGER NOT NULL,
                    PRIMARY KEY (source_id, token_position)
                );
                CREATE INDEX IF NOT EXISTS ix_fingerprints_value ON fingerprints(fingerprint);
                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            configured = {row["key"]: row["value"] for row in connection.execute("SELECT key,value FROM index_metadata")}
            if configured and (configured.get("k") != str(k) or configured.get("w") != str(w)):
                raise ValueError(
                    f"Index uses k={configured.get('k')} and w={configured.get('w')}; "
                    f"requested k={k} and w={w}. Use a new index database to change parameters."
                )
            if not configured:
                connection.executemany("INSERT INTO index_metadata(key,value) VALUES (?,?)", [("k", str(k)), ("w", str(w))])

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def add_document(self, source_id: str, title: str, text: str, *, source_url: str = "",
                     license_name: str = "") -> None:
        if not source_id:
            raise ValueError("source_id must not be empty")
        normalized = normalize_text(text)
        fingerprints = fingerprint_text(normalized, k=self.k, w=self.w)
        with self._connect() as connection:
            connection.execute("DELETE FROM reference_documents WHERE source_id=?", (source_id,))
            connection.execute(
                "INSERT INTO reference_documents(source_id,title,source_url,license_name,text,token_count) VALUES (?,?,?,?,?,?)",
                (source_id, title, source_url, license_name, text, len(normalized.tokens)),
            )
            connection.executemany(
                "INSERT INTO fingerprints(source_id,token_position,fingerprint,shingle,char_start,char_end) VALUES (?,?,?,?,?,?)",
                [(source_id, item.position, item.value, item.shingle, item.char_start, item.char_end)
                 for item in fingerprints],
            )

    def document_count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM reference_documents").fetchone()[0])

    def get_document(self, source_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM reference_documents WHERE source_id=?", (source_id,)).fetchone()
            return dict(row) if row else None

    def list_documents(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("SELECT source_id,title,source_url,license_name,token_count FROM reference_documents ORDER BY source_id").fetchall()
            return [dict(row) for row in rows]

    def candidates(self, fingerprints: list[Fingerprint]) -> list[dict]:
        """Return exact shingle matches for query fingerprints, grouped by seed."""
        if not fingerprints:
            return []
        by_hash: dict[str, list[Fingerprint]] = {}
        for item in fingerprints:
            by_hash.setdefault(item.value, []).append(item)
        hashes = list(by_hash)
        rows: list[sqlite3.Row] = []
        with self._connect() as connection:
            for offset in range(0, len(hashes), 500):
                batch = hashes[offset : offset + 500]
                placeholders = ",".join("?" for _ in batch)
                rows.extend(connection.execute(
                    f"SELECT source_id,token_position,fingerprint,shingle FROM fingerprints WHERE fingerprint IN ({placeholders})",
                    batch,
                ).fetchall())
        matches: list[dict] = []
        for row in rows:
            for query in by_hash[row["fingerprint"]]:
                # Guard the index against even a theoretical hash collision.
                if query.shingle == row["shingle"]:
                    matches.append({"source_id": row["source_id"], "query_position": query.position,
                                    "source_position": row["token_position"]})
        return matches
