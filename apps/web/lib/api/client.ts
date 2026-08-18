import { getApiBaseUrl } from "./config";
import { ApiError, describeApiErrorDetail, type ApiErrorBody } from "./errors";

export type ApiRequestInit = Omit<RequestInit, "body"> & { body?: unknown };

/**
 * Thin typed fetch wrapper shared by every endpoint module under `lib/api/`.
 * Always throws `ApiError` on failure (never a raw `Error`/`TypeError`), and
 * never caches (`cache: "no-store"`) so findings/dataset state stays live
 * during development, matching the "no fake results" requirement.
 */
export async function apiFetch<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const url = `${getApiBaseUrl()}${path}`;
  const { body, headers, ...rest } = init;

  let response: Response;
  try {
    response = await fetch(url, {
      // Session auth (TASK-053) is an httpOnly cookie on the API's own origin — always send it
      // unless a caller explicitly overrides.
      credentials: "include",
      ...rest,
      headers: { "content-type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiError({
      kind: "network",
      message: `Could not reach the API at ${url}.`,
      cause,
    });
  }

  const requestId = response.headers.get("x-request-id") ?? undefined;

  if (!response.ok) {
    const parsedBody = await readJsonSafely<ApiErrorBody>(response);
    const detailMessage = describeApiErrorDetail(parsedBody?.detail);
    throw new ApiError({
      kind: "http",
      status: response.status,
      requestId,
      detail: parsedBody?.detail,
      message: detailMessage ?? `Request to ${path} failed with status ${response.status}.`,
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const parsed = await readJsonSafely<T>(response);
  if (parsed === undefined) {
    throw new ApiError({
      kind: "http",
      status: response.status,
      requestId,
      message: `Response from ${path} was not valid JSON.`,
    });
  }
  return parsed;
}

async function readJsonSafely<T>(response: Response): Promise<T | undefined> {
  try {
    return (await response.json()) as T;
  } catch {
    return undefined;
  }
}
