import { api } from "../api/client";
import type { DocumentPage } from "../api/types";
import { useAsync, type AsyncState } from "./useAsync";

/**
 * The document list for the current filters.
 *
 * Both filters are applied server-side rather than by filtering the array here.
 * The client holds one page, not the corpus, so filtering in the browser would
 * silently narrow a page instead of the result set — right-looking on seven
 * documents and wrong on seven hundred.
 */
export function useDocuments(
  category: string | null,
  minSignificance: number | null,
): AsyncState<DocumentPage> {
  return useAsync(
    () =>
      api.listDocuments({
        category: category ?? undefined,
        min_significance: minSignificance ?? undefined,
      }),
    [category, minSignificance],
  );
}
