/**
 * Mirrors the Pydantic models in `api/models.py`.
 *
 * Hand-written rather than generated: the contract is three endpoints wide, and
 * a generator would be more machinery than the thing it maintains. The rule is
 * that this file changes only when `api/models.py` does.
 *
 * Note what is absent. There is no `confidence` — the pipeline computes a
 * relevance score during classification and never stores it, so the API cannot
 * report it. `significance` (1-5) is the value that is persisted and the one
 * that orders a list.
 */

export interface CategoryCount {
  slug: string;
  label: string;
  count: number;
}

/** A document as it appears in a list: metadata and a headline, no briefing body. */
export interface DocumentSummary {
  id: string;
  title: string;
  url: string;
  source: string;
  source_label: string;
  published: string;
  category: string;
  category_label: string;
  significance: number;
  excerpt: string;
}

/** A single document with its full briefing note. */
export interface DocumentDetail extends DocumentSummary {
  abstract: string | null;
  agencies: string[];
  doc_type: string | null;
  context: string;
  key_points: string[];
  india_impact: string;
  affected_sectors: string[];
  briefed_on: string;
}

export interface DocumentPage {
  items: DocumentSummary[];
  /** Matches before limit/offset — what a pager needs and `items.length` cannot say. */
  total: number;
}

/**
 * Every failure the UI can encounter, reduced to one shape.
 *
 * `kind` is what a component switches on; `message` is what it shows. Keeping
 * the distinction means copy can change without touching any logic.
 */
export type ApiErrorKind = "network" | "notFound" | "server" | "unknown";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;

  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}
