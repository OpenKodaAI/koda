import { QueryClient } from "@tanstack/react-query";
import { AppError, ValidationError, isAbortLikeError, toAppError } from "@/lib/errors";

export function createAppQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        gcTime: 3 * 60_000,
        refetchOnWindowFocus: false,
        retry(failureCount, error) {
          if (isAbortLikeError(error)) {
            return false;
          }

          const appError = toAppError(error);
          if (appError instanceof ValidationError) {
            return false;
          }

          if (appError.status >= 400 && appError.status < 500 && appError.status !== 429) {
            return false;
          }

          return failureCount < (appError.retryable ? 2 : 1);
        },
        retryDelay: (attemptIndex: number) =>
          Math.min(1000 * 2 ** attemptIndex, 30000) + Math.random() * 500,
      },
      mutations: {
        retry(_failureCount, error) {
          const appError =
            error instanceof AppError ? error : toAppError(error);
          return appError.retryable;
        },
        retryDelay: (attemptIndex: number) =>
          Math.min(1000 * 2 ** attemptIndex, 30000) + Math.random() * 500,
      },
    },
  });
}
