import type { DocumentSummary } from "../api/types";

/** Formatting only — no computation the API could have done. */
function formatDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function DocumentCard({
  document,
  selected,
  onSelect,
}: {
  document: DocumentSummary;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <article className={selected ? "card card--on" : "card"}>
      <button type="button" className="card__hit" onClick={() => onSelect(document.id)}>
        <header className="card__head">
          <span className="card__cat">{document.category_label}</span>
          <span
            className="card__sig"
            title={`Significance ${document.significance} of 5`}
            aria-label={`Significance ${document.significance} of 5`}
          >
            {"●".repeat(document.significance)}
            <span className="card__sig--off">{"●".repeat(5 - document.significance)}</span>
          </span>
        </header>

        <h3 className="card__title">{document.title}</h3>
        <p className="card__excerpt">{document.excerpt}</p>

        <footer className="card__foot">
          <span>{document.source_label}</span>
          <span>{formatDate(document.published)}</span>
        </footer>
      </button>
    </article>
  );
}
