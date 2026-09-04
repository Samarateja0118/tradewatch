"""FastAPI over the pipeline's SQLite file.

Thin on purpose. Every route does three things — validate input, run one
query, return a model — and there is no branch in here that decides what a
document *means*. That judgement already happened upstream; repeating any of
it would give the dashboard a second opinion that could disagree with the
digest it is supposed to be showing.

The database path comes from `TRADEWATCH_DB`. It falls back to the pipeline's
own `./tradewatch.db` when one exists — so running a pipeline and then the API
in one directory needs no configuration — and otherwise to the checked-in
snapshot, which is what a fresh clone and the deployed image both use.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import queries
from .models import CategoryCount, DocumentDetail, DocumentPage

def _default_db() -> Path:
    """A live run's database if there is one, else the snapshot that ships with the repo.

    Preferring the live file means a developer who has just run the pipeline
    sees their own data without setting anything; falling back to the snapshot
    means a fresh clone is never staring at an empty dashboard.
    """
    live = Path("./tradewatch.db")
    return live if live.exists() else Path("./data/snapshot.db")


DB_PATH = Path(os.getenv("TRADEWATCH_DB")) if os.getenv("TRADEWATCH_DB") else _default_db()

# A browser calling this from another origin is the normal case here: the
# frontend deploys to Vercel and the API somewhere else. Restricted to an
# explicit list rather than "*" so the deployed origin is a decision on the
# record instead of a default.
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("TRADEWATCH_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Opens the connection once, rather than per request.

    SQLite reads are cheap and the file is local; reconnecting per request
    would trade that for open() syscalls on every page view. `check_same_thread`
    is off in `connect`, which is safe here because the connection is read-only
    and SQLite serialises access internally.
    """
    if not DB_PATH.exists():
        # Failing at startup with the path in the message beats every request
        # returning an opaque 500 until someone thinks to check the volume.
        raise RuntimeError(
            f"No database at {DB_PATH.resolve()}. Run the pipeline, seed a snapshot "
            f"with `python -m scripts.seed_demo --db data/snapshot.db`, or set TRADEWATCH_DB."
        )
    app.state.db = queries.connect(DB_PATH)
    try:
        yield
    finally:
        app.state.db.close()


app = FastAPI(
    title="TradeWatch read API",
    description="Read-only access to briefings the TradeWatch pipeline has already produced.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def db(request_app: FastAPI = Depends(lambda: app)) -> sqlite3.Connection:
    return request_app.state.db


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/categories", response_model=list[CategoryCount])
def get_categories(conn: sqlite3.Connection = Depends(db)) -> list[CategoryCount]:
    return queries.list_categories(conn)


@app.get("/api/documents", response_model=DocumentPage)
def get_documents(
    category: str | None = Query(default=None, description="Category slug to filter by."),
    min_significance: int | None = Query(
        default=None,
        ge=1,
        le=5,
        description="Only briefings rated at least this significant (1-5). A floor, not an exact match.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conn: sqlite3.Connection = Depends(db),
) -> DocumentPage:
    return queries.list_documents(
        conn,
        category=category,
        min_significance=min_significance,
        limit=limit,
        offset=offset,
    )


@app.get("/api/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str, conn: sqlite3.Connection = Depends(db)) -> DocumentDetail:
    document = queries.get_document(conn, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No briefing exists for that document id")
    return document
