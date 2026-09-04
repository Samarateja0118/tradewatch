import { useEffect, useState } from "react";
import { ApiError } from "../api/types";

/**
 * `{ data, loading, error }` for one request, re-run when `deps` change.
 *
 * All three are always present, so a consumer that forgets to render a loading
 * or error branch has an obviously missing case rather than a blank screen.
 * That is the whole reason this is a shared hook: it makes the states
 * non-optional by construction instead of by discipline.
 *
 * A plain `useEffect` + `fetch` rather than TanStack Query. At three endpoints
 * with no refetching, no cache invalidation and no shared server state, the
 * library would be more concept than benefit — the things it buys (dedup,
 * stale-while-revalidate, background refresh) are all answers to problems this
 * page does not have yet.
 */
export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
}

export function useAsync<T>(run: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null });

  useEffect(() => {
    // Guards against a slow first request resolving after a faster second one
    // and overwriting it — the classic out-of-order render with a stale answer.
    let active = true;
    setState({ data: null, loading: true, error: null });

    run()
      .then((data) => {
        if (active) setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!active) return;
        const normalised =
          error instanceof ApiError ? error : new ApiError("unknown", "Something went wrong.");
        setState({ data: null, loading: false, error: normalised });
      });

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
