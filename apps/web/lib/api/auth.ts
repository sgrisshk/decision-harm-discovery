import { apiFetch } from "./client";
import type { User } from "./types";

// Mirrors apps/api/app/auth/routes.py.

export function login(email: string, password: string): Promise<User> {
  return apiFetch<User>("/api/v1/auth/login", { method: "POST", body: { email, password } });
}

export function logout(): Promise<void> {
  return apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
}

/** Throws `ApiError` with `status: 401` when nobody is logged in — callers should catch that
 * case explicitly rather than treating it as an unexpected failure. */
export function getCurrentUser(): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me");
}
