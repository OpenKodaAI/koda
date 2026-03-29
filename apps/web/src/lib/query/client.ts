import { QueryClient } from "@tanstack/react-query";
import { AppError, ValidationError, isAbortLikeError, toAppError } from "@/lib/errors";

export function createAppQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
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
      },
      mutations: {
        retry(_failureCount, error) {
          const appError =
            error instanceof AppError ? error : toAppError(error);
          return appError.retryable;
        },
      },
    },
  });
}
