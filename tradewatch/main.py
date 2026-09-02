"""Pipeline orchestration and CLI entry point.

    python -m tradewatch.main --days 1 --out ./briefs
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

import httpx

from .digest import render_html, render_markdown
from .llm import AnthropicClient
from .models import Digest, DigestEntry, RawDocument
from .pipeline.relevance import LLMClient, assess, prefilter
from .pipeline.summarize import heuristic_briefing, summarize
from .sources.federal_register import FederalRegisterSource
from .sources.rss import RSSSource
from .store import Store

log = logging.getLogger(__name__)


async def gather_documents(since: date) -> list[RawDocument]:
    """Fetch from all sources concurrently and deduplicate across them."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "tradewatch/0.1 (research project)"},
    ) as client:
        fr = FederalRegisterSource(client)
        rss = RSSSource(client)
        batches = await asyncio.gather(
            fr.fetch(since=since), rss.fetch(since=since), return_exceptions=True
        )

    docs: list[RawDocument] = []
    for batch in batches:
        if isinstance(batch, BaseException):
            log.error("A source failed entirely: %s", batch)
            continue
        docs.extend(batch)

    unique: dict[str, RawDocument] = {}
    for doc in docs:
        unique.setdefault(doc.content_hash, doc)
    return list(unique.values())


class ProcessResult(NamedTuple):
    """Entries for the digest, plus the counts the digest header reports."""

    entries: list[DigestEntry]
    considered: int  # documents not already briefed, i.e. actually filtered
    already_briefed: int


async def process(
    docs: list[RawDocument],
    llm: LLMClient | None,
    store: Store,
    *,
    threshold: float,
) -> ProcessResult:
    """Filter, assess, and summarize. Returns entries for the digest.

    `llm=None` runs the deterministic stages only — see `--no-llm`.
    """
    already_seen = store.seen_hashes()

    fresh = [d for d in docs if d.content_hash not in already_seen]
    candidates = [d for d in fresh if prefilter(d)]
    log.info(
        "Scanned %d documents: %d already briefed, prefilter dropped %d, "
        "%d candidates",
        len(docs),
        len(docs) - len(fresh),
        len(fresh) - len(candidates),
        len(candidates),
    )

    if llm is None:
        # Everything the prefilter kept becomes an entry. There is no
        # relevance stage to run without a model, so this is deliberately
        # over-inclusive — the reader does the filtering the model would.
        entries = []
        for doc in candidates:
            briefing = heuristic_briefing(doc)
            store.save_document(doc)
            store.save_briefing(briefing)
            entries.append(DigestEntry(document=doc, briefing=briefing))
        log.info("No-model mode: listed %d documents without assessment", len(entries))
        return ProcessResult(
            entries=entries,
            considered=len(fresh),
            already_briefed=len(docs) - len(fresh),
        )

    verdicts = await asyncio.gather(
        *(assess(d, llm, threshold=threshold) for d in candidates),
        return_exceptions=True,
    )

    relevant: list[RawDocument] = []
    for doc, verdict in zip(candidates, verdicts):
        if isinstance(verdict, BaseException):
            log.warning("Relevance check failed for %s: %s", doc.external_id, verdict)
            continue
        if verdict.is_relevant:
            relevant.append(doc)

    log.info("Relevance stage kept %d of %d", len(relevant), len(candidates))

    briefings = await asyncio.gather(
        *(summarize(d, llm) for d in relevant), return_exceptions=True
    )

    entries: list[DigestEntry] = []
    for doc, briefing in zip(relevant, briefings):
        if isinstance(briefing, BaseException):
            log.warning("Summarization failed for %s: %s", doc.external_id, briefing)
            continue
        store.save_document(doc)
        store.save_briefing(briefing)
        entries.append(DigestEntry(document=doc, briefing=briefing))

    return ProcessResult(
        entries=entries,
        considered=len(fresh),
        already_briefed=len(docs) - len(fresh),
    )


async def run(
    *, days: int, out_dir: Path, db_path: Path, threshold: float, use_llm: bool = True
) -> Digest:
    since = date.today() - timedelta(days=days)
    store = Store(db_path)
    llm = AnthropicClient() if use_llm else None

    docs = await gather_documents(since)
    result = await process(docs, llm, store, threshold=threshold)

    digest = Digest(
        digest_date=date.today(),
        entries=result.entries,
        documents_scanned=len(docs),
        # Only documents that actually went through filtering count as
        # filtered; ones already briefed on a previous run were deduplicated.
        documents_filtered=result.considered - len(result.entries),
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = digest.digest_date.isoformat()
    (out_dir / f"brief-{stamp}.md").write_text(render_markdown(digest))
    (out_dir / f"brief-{stamp}.html").write_text(render_html(digest))
    log.info("Wrote digest to %s", out_dir)

    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="India-US trade policy monitor")
    parser.add_argument("--days", type=int, default=1, help="Lookback window")
    parser.add_argument("--out", type=Path, default=Path("./briefs"))
    parser.add_argument("--db", type=Path, default=Path("./tradewatch.db"))
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip the model stages. Produces a categorised listing of "
        "documents that passed the keyword filter, with no relevance "
        "scoring and no impact analysis. Needs no API key.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    digest = asyncio.run(
        run(
            days=args.days,
            out_dir=args.out,
            db_path=args.db,
            threshold=args.threshold,
            use_llm=not args.no_llm,
        )
    )
    print(render_markdown(digest))


if __name__ == "__main__":
    main()
