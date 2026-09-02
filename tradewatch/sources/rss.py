"""RSS ingestion for USTR, Commerce and PIB India.

Government feeds are inconsistent — missing links, missing dates, occasional
malformed XML, and the odd HTML error page served with a 200. Every parse
failure here degrades to "skip this item" or "skip this feed", never to an
exception that kills the run.

Feed URLs are the least stable part of this project. They change without
notice, so verify them before relying on a scheduled run.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree

import httpx

from ..models import RawDocument, SourceType

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedConfig:
    url: str
    source: SourceType
    label: str


# Verified live on 2026-08-04. Only USTR is usable; see the notes below
# before re-adding anything here.
FEEDS = [
    FeedConfig(
        url="https://ustr.gov/rss.xml",
        source=SourceType.USTR,
        label="USTR",
    ),
]

# Checked and rejected — kept here so the next person does not re-derive it:
#
#   https://www.commerce.gov/feeds/news
#       403 behind a bot-detection challenge. Every commerce.gov RSS path
#       tried returns the same. Not accessible programmatically; use the
#       Federal Register, which carries Commerce/ITA determinations anyway.
#
#   https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3
#       200 and valid XML, but Hindi-only — the Lang parameter has no effect
#       (1, 2 and 3 all return identical Hindi content), and the documented
#       English paths (rss/lreleng.xml, Regid=0) return zero items.
#
# The USTR feed is also weaker than its name suggests: ~10 items, mixing
# state-level export blurbs with occasional stale entries (one dated 2009).
# It is real and parses cleanly, so it stays, but the Federal Register is
# doing nearly all the work in this pipeline.


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(value: str) -> str:
    """RSS `<description>` routinely carries escaped page markup.

    Left alone it reaches the digest verbatim — and worse, feeds the keyword
    prefilter, so class names and author slugs can trip a match.
    """
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", value))).strip()


def _text(item: ElementTree.Element, tag: str) -> str | None:
    node = item.find(tag)
    if node is None or node.text is None:
        return None
    value = _strip_html(node.text)
    return value or None


def _parse_date(raw: str | None) -> date | None:
    """RFC 822 is the RSS standard; ISO 8601 shows up anyway."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        log.debug("Unparseable RSS date: %r", raw)
        return None


def parse_feed(payload: bytes, config: FeedConfig) -> list[RawDocument]:
    """Parse one feed body. Returns [] rather than raising on garbage input."""
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        log.error("Malformed XML from %s: %s", config.label, exc)
        return []

    docs: list[RawDocument] = []
    for item in root.iter("item"):
        link = _text(item, "link")
        if not link:
            # Without a link there is nothing to cite, so the entry is useless
            # in a digest even if the title looks relevant.
            log.debug("Dropping %s item with no link", config.label)
            continue

        title = _text(item, "title")
        if not title:
            continue

        published = _parse_date(_text(item, "pubDate"))
        if published is None:
            # A dateless item can't be windowed, so treat it as today's.
            published = date.today()

        docs.append(
            RawDocument(
                source=config.source,
                external_id=link,
                title=title,
                url=link,
                published=published,
                abstract=_text(item, "description"),
                # Deliberately empty. `agencies` feeds searchable_text(), so
                # putting the feed label here would inject its words into
                # every document from that feed — a label like "PIB India
                # releases" made every item match the India prefilter and
                # earn a model call. The originating source is already
                # tracked in `source`.
                agencies=[],
                doc_type="press release",
            )
        )

    return docs


class RSSSource:
    """Fetches all configured feeds concurrently."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        feeds: list[FeedConfig] | None = None,
        *,
        max_concurrency: int = 4,
    ) -> None:
        self._client = client
        self._feeds = feeds if feeds is not None else FEEDS
        self._sem = asyncio.Semaphore(max_concurrency)

    async def _fetch_feed(self, config: FeedConfig, since: date) -> list[RawDocument]:
        async with self._sem:
            try:
                resp = await self._client.get(config.url, timeout=30.0)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.error("RSS fetch failed for %s: %s", config.label, exc)
                return []

        docs = parse_feed(resp.content, config)
        return [d for d in docs if d.published >= since]

    async def fetch(self, since: date | None = None) -> list[RawDocument]:
        since = since or (date.today() - timedelta(days=1))

        batches = await asyncio.gather(
            *(self._fetch_feed(c, since) for c in self._feeds),
            return_exceptions=True,
        )

        docs: list[RawDocument] = []
        for config, batch in zip(self._feeds, batches):
            if isinstance(batch, BaseException):
                # One bad feed must not cost us the others.
                log.error("RSS feed %s failed: %s", config.label, batch)
                continue
            docs.extend(batch)

        log.info("RSS: %d items since %s", len(docs), since)
        return docs
