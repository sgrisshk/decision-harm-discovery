"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getCurrentUser, logout } from "@/lib/api/auth";
import type { User } from "@/lib/api/types";

type AuthState = { state: "loading" } | { state: "anonymous" } | { state: "authenticated"; user: User };

/**
 * Shows the logged-in staff member (`TASK-053`) or a "Log in" link. Client component — the
 * session lives in an httpOnly cookie the server component tree can't read without a dedicated
 * server-side check, and this is display-only (no route in this app is gated on it yet, see
 * `docs/architecture/basic-authentication.md`).
 */
export function NavUser() {
  const [auth, setAuth] = useState<AuthState>({ state: "loading" });

  const refresh = useCallback(() => {
    // Any failure here (401 anonymous, or a network error) means "not logged in" for display
    // purposes — this component never surfaces an error state of its own.
    getCurrentUser()
      .then((user) => setAuth({ state: "authenticated", user }))
      .catch(() => setAuth({ state: "anonymous" }));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onLogout = useCallback(() => {
    logout()
      .then(() => setAuth({ state: "anonymous" }))
      .catch(() => setAuth({ state: "anonymous" }));
  }, []);

  if (auth.state === "loading") {
    return null;
  }

  if (auth.state === "anonymous") {
    return (
      <Link className="navUser navUser-login" href="/login">
        Log in
      </Link>
    );
  }

  return (
    <div className="navUser">
      <span className="navUser-email">{auth.user.email}</span>
      <button type="button" className="navUser-logout" onClick={onLogout}>
        Log out
      </button>
    </div>
  );
}
