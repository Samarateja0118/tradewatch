import { api } from "../api/client";
import type { CategoryCount } from "../api/types";
import { useAsync, type AsyncState } from "./useAsync";

export function useCategories(): AsyncState<CategoryCount[]> {
  return useAsync(() => api.listCategories(), []);
}
