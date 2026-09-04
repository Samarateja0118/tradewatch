"""Writes a small, realistic database without calling any model.

The real database is produced by a pipeline run and is gitignored, so a fresh
clone has nothing for the dashboard to show. This fills that gap for local
development and for screenshots — deterministic, offline, and costing no API
credit. It writes through `Store`, so what it produces has the same shape a
real run produces rather than a shape that only looks similar.

    python -m scripts.seed_demo --db ./tradewatch.db
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from tradewatch.models import Briefing, Category, RawDocument, SourceType
from tradewatch.store import Store

SEED: list[tuple[str, SourceType, Category, int, str, str, list[str], str, list[str]]] = [
    (
        "Certain Cold-Rolled Steel Flat Products from India: Preliminary Results of Administrative Review",
        SourceType.FEDERAL_REGISTER, Category.AD_CVD, 5,
        "Commerce proposes a lower dumping margin for Indian cold-rolled steel.",
        "Commerce reviews antidumping duties on Indian cold-rolled steel annually. This preliminary "
        "result covers the 2024-25 period and proposes a weighted-average margin materially below the "
        "rate currently in force.",
        ["Preliminary weighted-average margin falls to 2.38% from 7.60%",
         "Covers the period 1 September 2024 to 31 August 2025",
         "Final results expected within 120 days"],
        "A lower margin reduces landed cost for Indian mills shipping into the US and improves their "
        "position against Vietnamese and Korean suppliers. Exporters holding cash deposits at the "
        "higher rate may be entitled to refunds once the results are final.",
        ["Steel", "Metals"],
    ),
    (
        "Implementation of Additional Export Controls: Advanced Computing Items",
        SourceType.COMMERCE, Category.EXPORT_CONTROL, 5,
        "BIS widens licensing requirements for advanced computing hardware.",
        "The Bureau of Industry and Security expands controls on advanced computing integrated "
        "circuits and the equipment used to produce them, extending the licence requirement to "
        "additional destinations and adding a due-diligence obligation on resellers.",
        ["Adds a licence requirement for a wider band of compute performance",
         "Extends obligations to distributors and resellers",
         "Comment period runs 60 days from publication"],
        "India is not a restricted destination, but Indian system integrators reselling into "
        "restricted markets acquire a new diligence obligation. Data-centre operators sourcing "
        "accelerators should expect longer lead times.",
        ["Semiconductors", "Data Centres", "Electronics"],
    ),
    (
        "United States and India Conclude Sixth Round of Trade Policy Forum Talks",
        SourceType.USTR, Category.TRADE_AGREEMENT, 4,
        "Both sides report progress on market access; no binding text yet.",
        "The sixth round of the US-India Trade Policy Forum closed with a joint statement covering "
        "agricultural market access, digital trade and mutual recognition of standards. No binding "
        "instrument was signed.",
        ["Working groups established on digital trade and agriculture",
         "No tariff schedule changes announced",
         "Next round scheduled for the first quarter"],
        "Directionally positive for Indian agricultural exporters and IT services, but nothing here "
        "changes duties today. Treat as a signal of intent rather than a rule change.",
        ["Agriculture", "IT Services"],
    ),
    (
        "Notice of Proposed Rulemaking: Tariff Classification of Certain Textile Articles",
        SourceType.FEDERAL_REGISTER, Category.TARIFF, 3,
        "CBP proposes reclassifying a set of blended textile articles.",
        "Customs and Border Protection proposes moving certain man-made-fibre blended articles to a "
        "different tariff heading, changing the duty rate applied at entry.",
        ["Affects blended articles above a stated synthetic content threshold",
         "Proposed effective date is the start of the next quarter"],
        "Indian textile exporters shipping blended garments would see a duty change on affected "
        "lines. The threshold is what determines exposure, so classification review is worthwhile "
        "before the comment period closes.",
        ["Textiles", "Apparel"],
    ),
    (
        "India Notifies Revised Quality Control Orders for Electronics Imports",
        SourceType.PIB, Category.TECH_POLICY, 4,
        "BIS certification extended to a further category of imported electronics.",
        "India's Ministry of Electronics and IT notified revised Quality Control Orders extending "
        "mandatory BIS certification to additional imported electronic goods, with a transition "
        "window before enforcement.",
        ["Certification becomes mandatory after the transition window",
         "Applies to imports and domestic manufacture alike"],
        "US electronics exporters to India face a new pre-market certification step. Firms without "
        "an existing BIS registration should start early; the process has historically run longer "
        "than the notified window.",
        ["Electronics", "Consumer Goods"],
    ),
    (
        "Section 301 Investigation: Request for Comments on Digital Services Taxes",
        SourceType.USTR, Category.IPR, 3,
        "USTR reopens comments on digital services taxes affecting US firms.",
        "USTR requests public comment on digital services taxes maintained by several trading "
        "partners and whether they discriminate against US companies.",
        ["Comment period open for 45 days",
         "No new tariff action proposed at this stage"],
        "India's equalisation levy has featured in previous rounds of this investigation. A finding "
        "of discrimination is a precondition for tariff action, so this is the stage at which "
        "exposure is worth tracking.",
        ["Digital Services", "IT Services"],
    ),
    (
        "Foreign Investment Screening: Annual Report to Congress",
        SourceType.COMMERCE, Category.INVESTMENT, 2,
        "CFIUS reports rising review volume; approval rates broadly steady.",
        "The annual report to Congress summarises transaction volume, the share of filings taken to "
        "full investigation, and mitigation agreements imposed.",
        ["Filing volume up year on year",
         "Approval rate broadly unchanged"],
        "Indian acquirers in US technology and infrastructure should expect longer timelines, though "
        "nothing in the report signals a change in posture toward Indian capital specifically.",
        ["Investment", "Technology"],
    ),
]


def seed(db_path: Path) -> int:
    store = Store(db_path)
    today = date.today()

    for offset, (title, source, category, significance, headline, context, points, impact, sectors) in enumerate(SEED):
        published = today - timedelta(days=offset + 1)
        doc = RawDocument(
            source=source,
            external_id=f"demo-{offset:03d}",
            title=title,
            url=f"https://example.gov/demo/{offset:03d}",
            published=published,
            abstract=context[:280],
            agencies=[source.label],
            doc_type="Notice",
        )
        store.save_document(doc)
        store.save_briefing(
            Briefing(
                document_hash=doc.content_hash,
                headline=headline,
                context=context,
                key_points=points,
                india_impact=impact,
                category=category,
                significance=significance,
                affected_sectors=sectors,
            ),
            briefed_on=today,
        )

    store.close()
    return len(SEED)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("./tradewatch.db"))
    args = parser.parse_args()
    count = seed(args.db)
    print(f"Seeded {count} briefings into {args.db.resolve()}")


if __name__ == "__main__":
    main()
