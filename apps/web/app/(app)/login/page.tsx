import { Suspense } from "react";
import { LoginForm } from "@/components/auth/LoginForm";

export const metadata = {
  title: "Log in — Signal Foundry",
};

/**
 * Internal-staff login (`TASK-053`). No self-serve signup — accounts are created via
 * `scripts/create_user.py`. `LoginForm` reads `useSearchParams` (the `?next=` redirect target),
 * which requires a `Suspense` boundary for static prerendering.
 */
export default function LoginPage() {
  return (
    <>
      <div className="appPageHeader">
        <h1>Log in</h1>
        <p>Internal staff only — this identifies who records customer finding feedback.</p>
      </div>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </>
  );
}
