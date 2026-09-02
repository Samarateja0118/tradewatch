"""SQLite persistence.

Two things matter here. First, everything is keyed on `content_hash`, so
re-running the same day is idempotent and never re-summarizes a document
that already has a briefing. Second, `briefed_on` records the date a
briefing was *produced*, not the date the document was published — a
determination published last week and first seen today belongs in today's
digest.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

from .models import Briefing, Category, DigestEntry, RawDocument, SourceType

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    content_hash TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    published    TEXT NOT NULL,
    abstract     TEXT,
    agencies     TEXT NOT NULL DEFAULT '',
    doc_type     TEXT
);

CREATE TABLE IF NOT EXISTS briefings (
    document_hash    TEXT PRIMARY KEY REFERENCES documents(content_hash),
    headline         TEXT NOT NULL,
    context          TEXT NOT NULL,
    key_points       TEXT NOT NULL DEFAULT '',
    india_impact     TEXT NOT NULL,
    category         TEXT NOT NULL,
    significance     INTEGER NOT NULL,
    affected_sectors TEXT NOT NULL DEFAULT '',
    briefed_on       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS briefings_by_date ON briefings(briefed_on);
"""

# Lists are stored as newline-joined text. Sectors and key points are short
# free text without newlines, so this avoids a JSON round-trip per row.
_SEP = "\n"


def _pack(values: list[str]) -> str:
    return _SEP.join(v.replace(_SEP, " ") for v in values)


def _unpack(blob: str) -> list[str]:
    return [line for line in blob.split(_SEP) if line]


class Store:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def seen_hashes(self) -> set[str]:
        """Hashes that already have a briefing — the dedup gate for a run."""
        rows = self._conn.execute("SELECT document_hash FROM briefings").fetchall()
        return {row["document_hash"] for row in rows}

    def save_document(self, doc: RawDocument) -> None:
        self._conn.execute(
            """
            INSERT INTO documents
                (content_hash, source, external_id, title, url, published,
                 abstract, agencies, doc_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_hash) DO UPDATE SET
                url = excluded.url,
                abstract = excluded.abstract
            """,
            (
                doc.content_hash,
                doc.source.value,
                doc.external_id,
                doc.title,
                doc.url,
                doc.published.isoformat(),
                doc.abstract,
                _pack(doc.agencies),
                doc.doc_type,
            ),
        )
        self._conn.commit()

    def save_briefing(self, briefing: Briefing, briefed_on: date | None = None) -> None:
        """Idempotent: re-saving the same briefing updates it in place."""
        self._conn.execute(
            """
            INSERT INTO briefings
                (document_hash, headline, context, key_points, india_impact,
                 category, significance, affected_sectors, briefed_on)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_hash) DO UPDATE SET
                headline = excluded.headline,
                context = excluded.context,
                key_points = excluded.key_points,
                india_impact = excluded.india_impact,
                category = excluded.category,
                significance = excluded.significance,
                affected_sectors = excluded.affected_sectors
            """,
            (
                briefing.document_hash,
                briefing.headline,
                briefing.context,
                _pack(briefing.key_points),
                briefing.india_impact,
                briefing.category.value,
                briefing.significance,
                _pack(briefing.affected_sectors),
                (briefed_on or date.today()).isoformat(),
            ),
        )
        self._conn.commit()

    def entries_for(self, day: date) -> list[DigestEntry]:
        """Everything briefed on `day`, most significant first."""
        rows = self._conn.execute(
            """
            SELECT d.*, b.headline, b.context, b.key_points, b.india_impact,
                   b.category, b.significance, b.affected_sectors
            FROM briefings b
            JOIN documents d ON d.content_hash = b.document_hash
            WHERE b.briefed_on = ?
            ORDER BY b.significance DESC, d.published DESC
            """,
            (day.isoformat(),),
        ).fetchall()

        return [
            DigestEntry(
                document=RawDocument(
                    source=SourceType(row["source"]),
                    external_id=row["external_id"],
                    title=row["title"],
                    url=row["url"],
                    published=date.fromisoformat(row["published"]),
                    abstract=row["abstract"],
                    agencies=_unpack(row["agencies"]),
                    doc_type=row["doc_type"],
                ),
                briefing=Briefing(
                    document_hash=row["content_hash"],
                    headline=row["headline"],
                    context=row["context"],
                    key_points=_unpack(row["key_points"]),
                    india_impact=row["india_impact"],
                    category=Category(row["category"]),
                    significance=row["significance"],
                    affected_sectors=_unpack(row["affected_sectors"]),
                ),
            )
            for row in rows
        ]
