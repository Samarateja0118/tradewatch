"""Read-only access to the database the pipeline writes.

This module owns every SQL statement in the API. Two rules hold it in place:

1. **Nothing here writes.** The connection is opened in SQLite's read-only
   mode, so a stray INSERT fails loudly at the driver rather than quietly
   mutating the pipeline's data. The dashboard is a reader of a system it does
   not own.
2. **Nothing here reclassifies.** No thresholds, no scoring, no re-deriving a
   category. If a value is not in a column, it does not belong in a response —
   it belongs in the pipeline that produces the column.

Only documents that have a briefing are visible. The `documents` table also
holds rows the prefilter rejected, which were ingested but never judged
relevant; surfacing them would show the reader work-in-progress rather than
findings.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from tradewatch.models import Category, SourceType

from .models import CategoryCount, DocumentDetail, DocumentPage, DocumentSummary

_SEP = "\n"

# Mirrors Store._unpack. Duplicated rather than imported because the storage
# module owns a write path this one must not reach into; the coupling is to the
# column format, which is fixed, not to the class.
def _unpack(blob: str | None) -> list[str]:
    return [line for line in (blob or "").split(_SEP) if line]


_SUMMARY_COLUMNS = """
    d.content_hash AS id,
    d.title        AS title,
    d.url          AS url,
    d.source       AS source,
    d.published    AS published,
    b.category     AS category,
    b.significance AS significance,
    b.headline     AS excerpt
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """Opens the pipeline's database read-only.

    `mode=ro` rather than a convention or a code review promise: the guarantee
    that this process cannot write is worth having from the driver.
    """
    uri = f"file:{Path(path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _label_for_source(value: str) -> str:
    try:
        return SourceType(value).label
    except ValueError:
        # A source the API predates. Showing the raw slug beats 500ing over a
        # label, and the row is still perfectly readable.
        return value


def _label_for_category(value: str) -> str:
    try:
        return Category(value).label
    except ValueError:
        return value


def _summary(row: sqlite3.Row) -> DocumentSummary:
    return DocumentSummary(
        id=row["id"],
        title=row["title"],
        url=row["url"],
        source=row["source"],
        source_label=_label_for_source(row["source"]),
        published=date.fromisoformat(row["published"]),
        category=row["category"],
        category_label=_label_for_category(row["category"]),
        significance=row["significance"],
        excerpt=row["excerpt"],
    )


def list_documents(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> DocumentPage:
    """A page of briefed documents, most significant first.

    Ordering matches the digest's: significance descending, then publication
    date. A reader opening the dashboard should meet the same top item the
    briefing would have led with.
    """
    where = "WHERE b.category = ?" if category else ""
    params: list[object] = [category] if category else []

    total = conn.execute(
        f"""
        SELECT COUNT(*) AS n
        FROM briefings b
        JOIN documents d ON d.content_hash = b.document_hash
        {where}
        """,
        params,
    ).fetchone()["n"]

    rows = conn.execute(
        f"""
        SELECT {_SUMMARY_COLUMNS}
        FROM briefings b
        JOIN documents d ON d.content_hash = b.document_hash
        {where}
        ORDER BY b.significance DESC, d.published DESC, d.title ASC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()

    return DocumentPage(items=[_summary(r) for r in rows], total=total)


def get_document(conn: sqlite3.Connection, document_id: str) -> DocumentDetail | None:
    """One document with its briefing, or None if nothing is briefed under that id."""
    row = conn.execute(
        f"""
        SELECT {_SUMMARY_COLUMNS},
               d.abstract, d.agencies, d.doc_type,
               b.context, b.key_points, b.india_impact,
               b.affected_sectors, b.briefed_on
        FROM briefings b
        JOIN documents d ON d.content_hash = b.document_hash
        WHERE d.content_hash = ?
        """,
        (document_id,),
    ).fetchone()

    if row is None:
        return None

    return DocumentDetail(
        **_summary(row).model_dump(),
        abstract=row["abstract"],
        agencies=_unpack(row["agencies"]),
        doc_type=row["doc_type"],
        context=row["context"],
        key_points=_unpack(row["key_points"]),
        india_impact=row["india_impact"],
        affected_sectors=_unpack(row["affected_sectors"]),
        briefed_on=date.fromisoformat(row["briefed_on"]),
    )


def list_categories(conn: sqlite3.Connection) -> list[CategoryCount]:
    """Categories that actually hold documents, largest first.

    Empty categories are omitted deliberately: a filter offering a choice that
    returns nothing is a dead end the UI would then have to explain.
    """
    rows = conn.execute(
        """
        SELECT category, COUNT(*) AS n
        FROM briefings
        GROUP BY category
        ORDER BY n DESC, category ASC
        """
    ).fetchall()

    return [
        CategoryCount(slug=r["category"], label=_label_for_category(r["category"]), count=r["n"])
        for r in rows
    ]
