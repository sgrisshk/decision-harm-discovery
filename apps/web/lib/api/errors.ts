/**
 * Typed error handling for the API client.
 *
 * FastAPI's default error envelope is `{ "detail": ... }`, where `detail` is
 * either a plain string (raised `HTTPException`s, e.g. 404s) or a list of
 * validation-error objects (422s). `ApiError` normalizes both into a single
 * displayable message while preserving the raw detail for callers that need
 * it (e.g. a dev-only view).
 */

export type ApiValidationDetailItem = {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
};

export type ApiErrorDetail = string | ApiValidationDetailItem[];

export type ApiErrorBody = {
  detail?: ApiErrorDetail;
};

export type ApiErrorKind = "network" | "http";

export class ApiError extends Error {
  /** "network" = the request never reached the API. "http" = it did, and the API returned an error status. */
  readonly kind: ApiErrorKind;
  readonly status?: number;
  /** Echoes the backend's `x-request-id` response header, when present, for support/debugging. */
  readonly requestId?: string;
  readonly detail?: ApiErrorDetail;

  constructor(params: {
    kind: ApiErrorKind;
    message: string;
    status?: number;
    requestId?: string;
    detail?: ApiErrorDetail;
    cause?: unknown;
  }) {
    super(params.message, { cause: params.cause });
    this.name = "ApiError";
    this.kind = params.kind;
    this.status = params.status;
    this.requestId = params.requestId;
    this.detail = params.detail;
  }
}

export function describeApiErrorDetail(detail: ApiErrorDetail | undefined): string | null {
  if (!detail) {
    return null;
  }
  if (typeof detail === "string") {
    return detail;
  }
  return detail.map((item) => item.msg).join("; ") || null;
}
