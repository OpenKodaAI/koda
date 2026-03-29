export type AsyncActionState = "idle" | "pending" | "success" | "error";

export type MutationPolicy = "confirmed" | "optimistic" | "background";

export type LoadingVariant =
  | "route"
  | "section"
  | "list"
  | "panel"
  | "form"
  | "inline";

export type RefreshPolicy = "catalog" | "detail" | "live";

export type AsyncResourceState<T> = {
  data: T | null;
  initialLoading: boolean;
  refreshing: boolean;
  error: string | null;
  lastUpdated: number | null;
};

export type AsyncActionOptions<T> = {
  successMessage?: string;
  errorMessage?: string;
  silentSuccess?: boolean;
  silentError?: boolean;
  resetStatusAfterMs?: number;
  policy?: MutationPolicy;
  optimisticUpdate?: () => void;
  rollbackOptimistic?: () => void;
  onSuccess?: (result: T) => void | Promise<void>;
  onError?: (error: Error) => void | Promise<void>;
  onSettled?: () => void | Promise<void>;
};
