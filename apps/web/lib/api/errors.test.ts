import { describe, expect, it } from "vitest";
import { ApiError, describeApiErrorDetail } from "./errors";

describe("describeApiErrorDetail", () => {
  it("returns null when there is no detail", () => {
    expect(describeApiErrorDetail(undefined)).toBeNull();
  });

  it("passes a string detail through unchanged", () => {
    expect(describeApiErrorDetail("Dataset not found")).toBe("Dataset not found");
  });

  it("joins validation-error messages from a FastAPI 422 body", () => {
    const detail = describeApiErrorDetail([
      { type: "missing", loc: ["body", "name"], msg: "Field required" },
      { type: "string_too_short", loc: ["body", "source_filename"], msg: "String too short" },
    ]);
    expect(detail).toBe("Field required; String too short");
  });

  it("returns null for an empty validation-error list", () => {
    expect(describeApiErrorDetail([])).toBeNull();
  });
});

describe("ApiError", () => {
  it("carries kind/status/requestId/detail and is a real Error", () => {
    const error = new ApiError({
      kind: "http",
      status: 404,
      requestId: "req-123",
      detail: "Finding not found",
      message: "Finding not found",
    });

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
    expect(error.kind).toBe("http");
    expect(error.status).toBe(404);
    expect(error.requestId).toBe("req-123");
    expect(error.message).toBe("Finding not found");
  });

  it("preserves the underlying cause for a network failure", () => {
    const cause = new TypeError("fetch failed");
    const error = new ApiError({ kind: "network", message: "Could not reach the API", cause });

    expect(error.kind).toBe("network");
    expect(error.status).toBeUndefined();
    expect(error.cause).toBe(cause);
  });
});
