import type { CategoryCount } from "../api/types";
import type { DocumentSummary } from "../api/types";

/**
 * Three stat tiles rather than a chart.
 *
 * The numbers here answer "how much is there and how much of it matters" —
 * single headline values with no comparison to plot, which is the case where a
 * chart adds decoration and no information.
 */
export function StatBar({
  documents,
  categories,
  total,
}: {
  documents: DocumentSummary[];
  categories: CategoryCount[];
  total: number;
}) {
  // Counted from the page in hand rather than requested separately: this is a
  // description of what the reader is looking at, not a second query.
  const highPriority = documents.filter((d) => d.significance >= 4).length;

  return (
    <div className="stats">
      <div className="stat">
        <span className="stat__num">{total}</span>
        <span className="stat__lbl">briefings</span>
      </div>
      <div className="stat">
        <span className="stat__num">{highPriority}</span>
        <span className="stat__lbl">rated 4 or above</span>
      </div>
      <div className="stat">
        <span className="stat__num">{categories.length}</span>
        <span className="stat__lbl">policy areas</span>
      </div>
    </div>
  );
}
