"""Federal Register API client.

The Federal Register is the highest-value source for this agent: every
anti-dumping and countervailing duty determination, every tariff
proclamation, and every export control rule is published here on the day it
takes legal effect. No API key is required.

API docs: https://www.federalregister.gov/developers/documentation/api/v1
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Iterable

import httpx

from ..models import RawDocument, SourceType

log = logging.getLogger(__name__)

BASE_URL = "https://www.federalregister.gov/api/v1/documents.json"

FIELDS = [
    "document_number",
    "title",
    "abstract",
    "html_url",
    "publication_date",
    "type",
    "agencies",
]

# Agencies whose notices are worth scanning. Narrowing at the API level is
# far cheaper than filtering thousands of unrelated documents downstream.
AGENCY_SLUGS = [
    "international-trade-administration",
    "international-trade-commission",
    "commerce-department",
    "trade-representative-office-of-united-states",
    "industry-and-security-bureau",
]

SEARCH_TERMS = [
    "India",
    "antidumping",
    "countervailing duty",
    "tariff",
    "trade agreement",
]


def _parse_agencies(raw: Any) -> list[str]:
    """Agency payloads vary: sometimes dicts, sometimes bare strings."""
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("raw_name")
            if name:
                names.append(str(name))
        elif isinstance(item, str):
            names.append(item)
    return names


def parse_document(payload: dict[str, Any]) -> RawDocument | None:
    """Convert one API result into a RawDocument.

    Returns None rather than raising on malformed records: a single bad row
    should not abort the day's ingestion.
    """
    try:
        return RawDocument(
            source=SourceType.FEDERAL_REGISTER,
            external_id=str(payload["document_number"]),
            title=payload["title"],
            url=payload["html_url"],
            published=date.fromisoformat(payload["publication_date"]),
            abstract=payload.get("abstract"),
            agencies=_parse_agencies(payload.get("agencies")),
            doc_type=payload.get("type"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        log.warning("Skipping malformed Federal Register record: %s", exc)
        return None


class FederalRegisterSource:
    """Fetches recent trade-related documents from the Federal Register."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        per_page: int = 100,
        max_concurrency: int = 4,
        max_pages: int = 10,
    ) -> None:
        self._client = client
        self._per_page = per_page
        self._max_pages = max_pages
        self._sem = asyncio.Semaphore(max_concurrency)

    async def _fetch_page(
        self, term: str, since: date, page: int
    ) -> dict[str, Any] | None:
        """One page of results, or None if the request or its body was bad."""
        params: list[tuple[str, str]] = [
            ("per_page", str(self._per_page)),
            ("page", str(page)),
            ("order", "newest"),
            ("conditions[term]", term),
            ("conditions[publication_date][gte]", since.isoformat()),
        ]
        params += [("fields[]", f) for f in FIELDS]

        async with self._sem:
            try:
                resp = await self._client.get(BASE_URL, params=params, timeout=30.0)
                resp.raise_for_status()
                body = resp.json()
            except httpx.HTTPError as exc:
                log.error(
                    "Federal Register fetch failed for %r page %d: %s", term, page, exc
                )
                return None
            except ValueError as exc:
                # A 200 carrying an error page rather than JSON. Degrade the
                # one request, not the whole source.
                log.error(
                    "Federal Register returned non-JSON for %r page %d: %s",
                    term,
                    page,
                    exc,
                )
                return None

        return body if isinstance(body, dict) else None

    async def _fetch_term(self, term: str, since: date) -> list[RawDocument]:
        """All pages for one search term, up to `max_pages`."""
        docs: list[RawDocument] = []
        page = 1
        while page <= self._max_pages:
            body = await self._fetch_page(term, since, page)
            if body is None:
                break

            results = body.get("results") or []
            docs.extend(d for d in map(parse_document, results) if d is not None)

            total_pages = body.get("total_pages")
            if not isinstance(total_pages, int) or page >= total_pages:
                break
            page += 1
        else:
            log.warning(
                "Federal Register: hit the %d-page cap for %r; results truncated. "
                "Narrow the lookback window or raise max_pages.",
                self._max_pages,
                term,
            )

        return docs

    async def fetch(
        self, since: date | None = None, terms: Iterable[str] | None = None
    ) -> list[RawDocument]:
        """Fetch documents published on or after `since`, deduplicated.

        Terms are queried concurrently; overlap between them is expected and
        collapsed on document number.
        """
        since = since or (date.today() - timedelta(days=1))
        terms = list(terms or SEARCH_TERMS)

        batches = await asyncio.gather(
            *(self._fetch_term(t, since) for t in terms), return_exceptions=True
        )

        seen: dict[str, RawDocument] = {}
        for term, batch in zip(terms, batches):
            if isinstance(batch, BaseException):
                # One term failing must not cost us the other four.
                log.error("Federal Register term %r failed: %s", term, batch)
                continue
            for doc in batch:
                seen.setdefault(doc.external_id, doc)

        log.info(
            "Federal Register: %d unique documents since %s", len(seen), since
        )
        return list(seen.values())
