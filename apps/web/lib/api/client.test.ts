import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "./client";
import { ApiError } from "./errors";

const originalFetch = global.fetch;

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.unstubAllEnvs();
});

function jsonResponse(body: unknown, init: ResponseInit & { requestId?: string } = {}) {
  const headers = new Headers(init.headers);
  if (init.requestId) {
    headers.set("x-request-id", init.requestId);
  }
  return new Response(JSON.stringify(body), { ...init, headers });
}

describe("apiFetch", () => {
  it("returns parsed JSON on a successful response", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));

    const result = await apiFetch<{ status: string }>("/health");

    expect(result).toEqual({ status: "ok" });
    expect(global.fetch).toHaveBeenCalledWith(
      "http://api.test/health",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("throws a network-kind ApiError when fetch itself rejects", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(apiFetch("/health")).rejects.toMatchObject({
      name: "ApiError",
      kind: "network",
    });
  });

  it("throws an http-kind ApiError with the FastAPI string detail on a 404", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse({ detail: "Finding not found" }, { status: 404, requestId: "req-abc" }),
    );

    let caught: unknown;
    try {
      await apiFetch("/api/v1/findings/missing");
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(ApiError);
    const apiError = caught as ApiError;
    expect(apiError.kind).toBe("http");
    expect(apiError.status).toBe(404);
    expect(apiError.requestId).toBe("req-abc");
    expect(apiError.message).toBe("Finding not found");
  });

  it("throws an http-kind ApiError describing a 422 validation-error list", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse(
        { detail: [{ type: "missing", loc: ["body", "name"], msg: "Field required" }] },
        { status: 422 },
      ),
    );

    await expect(apiFetch("/api/v1/datasets")).rejects.toMatchObject({
      kind: "http",
      status: 422,
      message: "Field required",
    });
  });

  it("returns undefined for a 204 response without attempting to parse a body", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));

    await expect(apiFetch("/api/v1/whatever")).resolves.toBeUndefined();
  });
});
