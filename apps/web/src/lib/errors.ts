export type AppErrorCode =
  | "UNKNOWN"
  | "API_ERROR"
  | "VALIDATION_ERROR"
  | "UPSTREAM_UNAVAILABLE"
  | "NOT_FOUND"
  | "UNAUTHORIZED"
  | "FORBIDDEN";

type AppErrorOptions = {
  code?: AppErrorCode;
  status?: number;
  cause?: unknown;
  retryable?: boolean;
  exposeMessage?: boolean;
};

export class AppError extends Error {
  code: AppErrorCode;
  status: number;
  cause?: unknown;
  retryable: boolean;
  exposeMessage: boolean;

  constructor(message: string, options: AppErrorOptions = {}) {
    super(message);
    this.name = "AppError";
    this.code = options.code ?? "UNKNOWN";
    this.status = options.status ?? 500;
    this.cause = options.cause;
    this.retryable = options.retryable ?? false;
    this.exposeMessage = options.exposeMessage ?? false;
  }
}

export class ValidationError extends AppError {
  fieldErrors?: Record<string, string[]>;

  constructor(
    message: string,
    options: Omit<AppErrorOptions, "code" | "status"> & {
      fieldErrors?: Record<string, string[]>;
    } = {},
  ) {
    super(message, {
      ...options,
      code: "VALIDATION_ERROR",
      status: 400,
      exposeMessage: true,
    });
    this.name = "ValidationError";
    this.fieldErrors = options.fieldErrors;
  }
}

export class ApiError extends AppError {
  constructor(message: string, status = 500, options: Omit<AppErrorOptions, "code" | "status"> = {}) {
    super(message, {
      ...options,
      code: status === 401
        ? "UNAUTHORIZED"
        : status === 403
          ? "FORBIDDEN"
          : status === 404
            ? "NOT_FOUND"
            : "API_ERROR",
      status,
      retryable: options.retryable ?? status >= 500,
      exposeMessage: true,
    });
    this.name = "ApiError";
  }
}

export class UpstreamUnavailableError extends ApiError {
  constructor(message: string, options: Omit<AppErrorOptions, "code" | "status"> = {}) {
    super(message, 503, {
      ...options,
      retryable: true,
    });
    this.name = "UpstreamUnavailableError";
    this.code = "UPSTREAM_UNAVAILABLE";
  }
}

export function isAbortLikeError(error: unknown) {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

export function toAppError(
  error: unknown,
  fallbackMessage = "Unable to complete the request.",
): AppError {
  if (error instanceof AppError) {
    return error;
  }

  if (isAbortLikeError(error)) {
    return new AppError("Request aborted", {
      status: 499,
      cause: error,
      retryable: false,
    });
  }

  if (error instanceof Error) {
    return new AppError(error.message || fallbackMessage, {
      cause: error,
      retryable: false,
      exposeMessage: true,
    });
  }

  return new AppError(fallbackMessage, {
    cause: error,
  });
}

export function toPublicErrorMessage(
  error: unknown,
  fallbackMessage = "Unable to complete the request.",
) {
  const appError = toAppError(error, fallbackMessage);
  return appError.exposeMessage && appError.message.trim()
    ? appError.message
    : fallbackMessage;
}
