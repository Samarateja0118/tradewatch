"""Digest rendering — markdown and HTML.

Both renderers sort by significance, so the reader sees the anti-dumping
determination before the procedural notice. An empty digest renders cleanly
rather than producing a blank page: "nothing relevant today" is a useful
result, not a failure.
"""

from __future__ import annotations

from html import escape

from .models import Digest, DigestEntry

EMPTY_MESSAGE = "No relevant developments in this window."


def _stars(significance: int) -> str:
    return "●" * significance + "○" * (5 - significance)


def _entry_markdown(entry: DigestEntry) -> str:
    doc, brief = entry.document, entry.briefing
    lines = [
        f"### {brief.headline}",
        "",
        f"**{brief.category.label}** · {_stars(brief.significance)} · "
        f"{doc.source.label} · {doc.published.isoformat()}",
        "",
        brief.context,
        "",
    ]

    if brief.key_points:
        lines += [f"- {point}" for point in brief.key_points] + [""]

    lines += ["**Impact on India:** " + brief.india_impact, ""]

    if brief.affected_sectors:
        lines += ["*Sectors:* " + ", ".join(brief.affected_sectors), ""]

    lines += [f"[{doc.title}]({doc.url})", ""]
    return "\n".join(lines)


def render_markdown(digest: Digest) -> str:
    header = [
        f"# India–US Trade Brief — {digest.digest_date.isoformat()}",
        "",
        f"Scanned {digest.documents_scanned} documents, "
        f"filtered {digest.documents_filtered}, "
        f"briefed {len(digest.entries)}.",
        "",
    ]

    if not digest.entries:
        return "\n".join(header + [EMPTY_MESSAGE, ""])

    body = [_entry_markdown(e) for e in digest.by_significance()]
    return "\n".join(header + ["---", ""] + body)


_CSS = """
body { font: 16px/1.6 Georgia, serif; max-width: 46rem; margin: 3rem auto;
       padding: 0 1.25rem; color: #1c1a17; background: #faf8f4; }
h1 { font-size: 1.6rem; border-bottom: 2px solid #c25a3a; padding-bottom: .5rem; }
h2 { font-size: 1.15rem; margin: 0 0 .35rem; }
article { border-top: 1px solid #ddd6c9; padding: 1.5rem 0; }
.meta { font-size: .8rem; letter-spacing: .04em; text-transform: uppercase;
        color: #6b6459; margin-bottom: .9rem; }
.impact { background: #f2ece1; border-left: 3px solid #c25a3a;
          padding: .75rem 1rem; margin: 1rem 0; }
.sectors { font-size: .85rem; color: #6b6459; font-style: italic; }
a { color: #a2452c; }
.summary { color: #6b6459; font-size: .9rem; }
"""


def _entry_html(entry: DigestEntry) -> str:
    doc, brief = entry.document, entry.briefing
    parts = [
        "<article>",
        f"<h2>{escape(brief.headline)}</h2>",
        f'<p class="meta">{escape(brief.category.label)} &middot; '
        f"{_stars(brief.significance)} &middot; {escape(doc.source.label)} &middot; "
        f"{doc.published.isoformat()}</p>",
        f"<p>{escape(brief.context)}</p>",
    ]

    if brief.key_points:
        points = "".join(f"<li>{escape(p)}</li>" for p in brief.key_points)
        parts.append(f"<ul>{points}</ul>")

    parts.append(
        f'<p class="impact"><strong>Impact on India:</strong> '
        f"{escape(brief.india_impact)}</p>"
    )

    if brief.affected_sectors:
        sectors = escape(", ".join(brief.affected_sectors))
        parts.append(f'<p class="sectors">Sectors: {sectors}</p>')

    parts.append(f'<p><a href="{escape(doc.url)}">{escape(doc.title)}</a></p>')
    parts.append("</article>")
    return "\n".join(parts)


def render_html(digest: Digest) -> str:
    stamp = digest.digest_date.isoformat()
    body = (
        "\n".join(_entry_html(e) for e in digest.by_significance())
        if digest.entries
        else f"<p>{EMPTY_MESSAGE}</p>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>India&ndash;US Trade Brief &mdash; {stamp}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>India&ndash;US Trade Brief &mdash; {stamp}</h1>
<p class="summary">Scanned {digest.documents_scanned} documents, filtered
{digest.documents_filtered}, briefed {len(digest.entries)}.</p>
{body}
</body>
</html>
"""
