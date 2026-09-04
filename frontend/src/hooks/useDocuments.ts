import { api } from "../api/client";
import type { DocumentPage } from "../api/types";
import { useAsync, type AsyncState } from "./useAsync";

/** The document list for the selected category, or all of them when none is selected. */
export function useDocuments(category: string | null): AsyncState<DocumentPage> {
  return useAsync(() => api.listDocuments({ category: category ?? undefined }), [category]);
}
