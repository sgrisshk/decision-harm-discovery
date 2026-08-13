/**
 * Resolves the API base URL from the environment.
 *
 * `NEXT_PUBLIC_API_URL` is read as a literal `process.env.NEXT_PUBLIC_API_URL`
 * expression (not aliased or destructured) so Next.js can inline it at build
 * time for both server and client bundles.
 */

const DEV_FALLBACK_API_URL = "http://localhost:8000";

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured && configured.trim().length > 0) {
    return configured.trim().replace(/\/+$/, "");
  }

  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "NEXT_PUBLIC_API_URL is not set. Production builds must not assume a default API URL.",
    );
  }

  return DEV_FALLBACK_API_URL;
}
