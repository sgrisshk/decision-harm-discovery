import { ApiError } from "./errors";

/**
 * Turns anything a data-fetching call might throw into safe-to-render text
 * for `<ErrorState />`. Centralized so every page handles `ApiError` (and
 * the unexpected non-`ApiError` case) the same way.
 */
export function toErrorDisplay(error: unknown): { message: string; requestId?: string } {
  if (error instanceof ApiError) {
    return { message: error.message, requestId: error.requestId };
  }
  return { message: "An unexpected error occurred." };
}
