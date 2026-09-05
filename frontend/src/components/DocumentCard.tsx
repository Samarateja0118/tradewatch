import type { DocumentSummary } from "../api/types";
import { SignificanceMeter } from "./SignificanceMeter";

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
          <SignificanceMeter value={document.significance} />
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
