"""The read API against a database the pipeline itself wrote.

The fixture builds its data through `Store`, not through hand-written SQL. If
the pipeline's schema moves, these tests move with it and fail honestly;
inserting rows directly would let the API keep passing against a shape that no
longer exists.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from tradewatch.models import Briefing, Category, RawDocument, SourceType
from tradewatch.store import Store


def _document(title: str, published: date, source: SourceType) -> RawDocument:
    return RawDocument(
        source=source,
        external_id=title.lower().replace(" ", "-"),
        title=title,
        url=f"https://example.test/{title.lower().replace(' ', '-')}",
        published=published,
        abstract=f"Abstract for {title}.",
        agencies=["Department of Commerce"],
        doc_type="Notice",
    )


def _briefing(doc: RawDocument, category: Category, significance: int) -> Briefing:
    return Briefing(
        document_hash=doc.content_hash,
        headline=f"Headline for {doc.title}",
        context=f"Context paragraph for {doc.title}.",
        key_points=["First point", "Second point"],
        india_impact="Moderate exposure for exporters.",
        category=category,
        significance=significance,
        affected_sectors=["Steel", "Chemicals"],
    )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "tradewatch.db"
    store = Store(db_path)

    seeded = [
        (_document("Steel duty review", date(2026, 8, 1), SourceType.FEDERAL_REGISTER), Category.AD_CVD, 5),
        (_document("Tariff schedule update", date(2026, 8, 2), SourceType.USTR), Category.TARIFF, 3),
        (_document("Chip export rule", date(2026, 8, 3), SourceType.COMMERCE), Category.EXPORT_CONTROL, 4),
        (_document("Second duty notice", date(2026, 7, 30), SourceType.FEDERAL_REGISTER), Category.AD_CVD, 2),
    ]
    for doc, category, significance in seeded:
        store.save_document(doc)
        store.save_briefing(_briefing(doc, category, significance), briefed_on=date(2026, 8, 4))

    # An ingested document that was never briefed — the API must not show it.
    store.save_document(_document("Unrelated filing", date(2026, 8, 1), SourceType.PIB))
    store.close()

    monkeypatch.setenv("TRADEWATCH_DB", str(db_path))
    import importlib

    from api import app as app_module

    importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        c.seeded = seeded  # type: ignore[attr-defined]
        yield c


def test_lists_documents_most_significant_first(client):
    body = client.get("/api/documents").json()

    assert body["total"] == 4
    assert [item["significance"] for item in body["items"]] == [5, 4, 3, 2]


def test_omits_documents_that_have_no_briefing(client):
    titles = [item["title"] for item in client.get("/api/documents").json()["items"]]

    assert "Unrelated filing" not in titles


def test_filters_by_category_and_reports_the_filtered_total(client):
    body = client.get("/api/documents", params={"category": "ad_cvd"}).json()

    assert body["total"] == 2
    assert {item["category"] for item in body["items"]} == {"ad_cvd"}


def test_total_counts_matches_not_the_page(client):
    """`total` is what a pager needs, and `len(items)` cannot supply it."""
    body = client.get("/api/documents", params={"limit": 1}).json()

    assert len(body["items"]) == 1
    assert body["total"] == 4


def test_list_items_carry_no_briefing_body(client):
    item = client.get("/api/documents").json()["items"][0]

    assert item["excerpt"]
    for absent in ("context", "key_points", "india_impact", "affected_sectors"):
        assert absent not in item


def test_detail_carries_the_full_briefing(client):
    listed = client.get("/api/documents").json()["items"][0]

    detail = client.get(f"/api/documents/{listed['id']}").json()

    assert detail["id"] == listed["id"]
    assert detail["context"].startswith("Context paragraph")
    assert detail["key_points"] == ["First point", "Second point"]
    assert detail["affected_sectors"] == ["Steel", "Chemicals"]
    assert detail["briefed_on"] == "2026-08-04"


def test_unknown_document_is_a_404(client):
    response = client.get("/api/documents/" + "0" * 64)

    assert response.status_code == 404


def test_categories_carry_labels_and_counts(client):
    categories = client.get("/api/categories").json()

    by_slug = {c["slug"]: c for c in categories}
    assert by_slug["ad_cvd"]["count"] == 2
    assert by_slug["ad_cvd"]["label"] == "Anti-Dumping / Countervailing Duty"
    # Ordered largest first, so the filter leads with the busiest category.
    assert [c["count"] for c in categories] == sorted((c["count"] for c in categories), reverse=True)


def test_categories_omit_those_with_no_documents(client):
    slugs = {c["slug"] for c in client.get("/api/categories").json()}

    assert "ipr" not in slugs


def test_the_api_cannot_write_to_the_pipelines_database(client):
    """The read-only guarantee, asserted rather than promised."""
    import sqlite3

    with pytest.raises(sqlite3.OperationalError):
        client.app.state.db.execute("DELETE FROM briefings")
