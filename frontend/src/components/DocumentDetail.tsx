import type { DocumentDetail as Detail } from "../api/types";

/**
 * The full briefing note, in the order the pipeline writes it: context, then
 * what happened, then what it means for India. That structure is the product —
 * flattening it into prose here would discard the thing the LLM was asked for.
 */
export function DocumentDetail({ document, onClose }: { document: Detail; onClose: () => void }) {
  return (
    <article className="detail">
      <button type="button" className="detail__close" onClick={onClose} aria-label="Close briefing">
        ×
      </button>

      <span className="detail__cat">{document.category_label}</span>
      <h2 className="detail__title">{document.title}</h2>
      <p className="detail__headline">{document.excerpt}</p>

      <section>
        <h4>Context</h4>
        <p>{document.context}</p>
      </section>

      {document.key_points.length > 0 && (
        <section>
          <h4>Key points</h4>
          <ul>
            {document.key_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h4>Impact on India</h4>
        <p>{document.india_impact}</p>
      </section>

      {document.affected_sectors.length > 0 && (
        <section>
          <h4>Affected sectors</h4>
          <p className="detail__sectors">
            {document.affected_sectors.map((sector) => (
              <span key={sector} className="tag">
                {sector}
              </span>
            ))}
          </p>
        </section>
      )}

      <footer className="detail__foot">
        <dl>
          <dt>Source</dt>
          <dd>{document.source_label}</dd>
          <dt>Published</dt>
          <dd>{document.published}</dd>
          <dt>Briefed</dt>
          <dd>{document.briefed_on}</dd>
          {document.agencies.length > 0 && (
            <>
              <dt>Agencies</dt>
              <dd>{document.agencies.join(", ")}</dd>
            </>
          )}
        </dl>
        <a href={document.url} target="_blank" rel="noopener noreferrer">
          Read the original ↗
        </a>
      </footer>
    </article>
  );
}
