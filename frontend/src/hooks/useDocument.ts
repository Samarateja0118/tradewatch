import { api } from "../api/client";
import type { DocumentDetail } from "../api/types";
import { useAsync, type AsyncState } from "./useAsync";

/** One document's full briefing. Idle — not loading — while nothing is selected. */
export function useDocument(id: string | null): AsyncState<DocumentDetail> {
  const state = useAsync(
    () => (id ? api.getDocument(id) : Promise.resolve(null as unknown as DocumentDetail)),
    [id],
  );
  return id ? state : { data: null, loading: false, error: null };
}
