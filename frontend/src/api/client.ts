import { ApiError, type CategoryCount, type DocumentDetail, type DocumentPage } from "./types";

/**
 * The only place that knows about HTTP.
 *
 * Errors are normalised here so no component ever handles a raw fetch
 * rejection: a dropped connection, a 404 and a 500 all arrive as `ApiError`
 * with a `kind` the UI can switch on. That is the same instinct as the retry
 * and circuit-breaking layer in the pipeline's TMDB gateway — failures get a
 * vocabulary at the boundary, so nothing above has to understand the transport.
 */

const BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(BASE_URL + path);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }

  let response: Response;
  try {
    response = await fetch(url);
  } catch (cause) {
    // fetch rejects only when the request never completed — no server, DNS
    // failure, connection dropped. An HTTP error status resolves instead.
    throw new ApiError("network", "Could not reach the API.", undefined);
  }

  if (!response.ok) {
    if (response.status === 404) {
      throw new ApiError("notFound", "That briefing does not exist.", 404);
    }
    if (response.status >= 500) {
      throw new ApiError("server", "The API failed to answer.", response.status);
    }
    throw new ApiError("unknown", `Request failed (${response.status}).`, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    // A 200 whose body is not JSON is a broken server, not a broken request.
    throw new ApiError("server", "The API returned something that was not JSON.", response.status);
  }
}

export const api = {
  listDocuments: (
    params: { category?: string; min_significance?: number; limit?: number; offset?: number } = {},
  ) =>
    request<DocumentPage>("/api/documents", params),

  getDocument: (id: string) => request<DocumentDetail>(`/api/documents/${encodeURIComponent(id)}`),

  listCategories: () => request<CategoryCount[]>("/api/categories"),
};

export type Api = typeof api;
