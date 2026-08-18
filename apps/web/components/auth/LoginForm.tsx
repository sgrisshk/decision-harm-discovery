"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
import { login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/errors";

type FormState = { state: "idle" | "submitting" } | { state: "error"; message: string };

/**
 * Internal-staff login (`TASK-053`) — no self-serve signup, see `scripts/create_user.py`. On
 * success, redirects to `?next=` if present (how `FeedbackForm` sends an anonymous reviewer here)
 * or `/findings` otherwise.
 */
export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [form, setForm] = useState<FormState>({ state: "idle" });

  const onSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setForm({ state: "submitting" });
      login(email, password)
        .then(() => {
          const next = searchParams.get("next");
          router.push(next && next.startsWith("/") ? next : "/findings");
          router.refresh();
        })
        .catch((error: unknown) => {
          const message =
            error instanceof ApiError ? error.message : "An unexpected error occurred.";
          setForm({ state: "error", message });
        });
    },
    [email, password, router, searchParams],
  );

  return (
    <form className="loginForm" onSubmit={onSubmit}>
      <label className="loginForm-field">
        <span>Email</span>
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>
      <label className="loginForm-field">
        <span>Password</span>
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      {form.state === "error" && (
        <p className="loginForm-error" role="alert">
          {form.message}
        </p>
      )}
      <button type="submit" className="loginForm-submit" disabled={form.state === "submitting"}>
        {form.state === "submitting" ? "Logging in…" : "Log in"}
      </button>
    </form>
  );
}
