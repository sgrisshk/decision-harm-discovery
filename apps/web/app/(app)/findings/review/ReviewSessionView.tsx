"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { EvidencePill } from "@/components/findings/EvidencePill";
import { FindingCoreContent } from "@/components/findings/FindingCoreContent";
import { ReadinessPill } from "@/components/findings/ReadinessPill";
import { ReviewQueueForm } from "@/components/findings/ReviewQueueForm";
import { WarningBadge } from "@/components/findings/WarningBadge";
import { getCurrentUser } from "@/lib/api/auth";
import { toErrorDisplay } from "@/lib/api/display";
import { listFindings } from "@/lib/api/findings";
import { sortFindings } from "../sortFindings";
import type { Finding } from "@/lib/api/types";

type AuthState = "loading" | "anonymous" | "authenticated";
type Result = { attempt: number } & ({ findings: Finding[] } | { error: unknown });

const LAST_SESSION_NAME_KEY = "sf-review-last-session-name";

type Progress = { savedIds: string[]; skippedIds: string[] };

function progressKey(reviewSession: string): string {
  return `sf-review-session:${reviewSession}`;
}

function loadProgress(reviewSession: string): Progress {
  try {
    const raw = window.localStorage.getItem(progressKey(reviewSession));
    if (!raw) return { savedIds: [], skippedIds: [] };
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      Array.isArray((parsed as Progress).savedIds) &&
      Array.isArray((parsed as Progress).skippedIds)
    ) {
      return parsed as Progress;
    }
  } catch {
    // Corrupt or unavailable storage — start fresh rather than fail the whole session.
  }
  return { savedIds: [], skippedIds: [] };
}

function saveProgress(reviewSession: string, progress: Progress): void {
  try {
    window.localStorage.setItem(progressKey(reviewSession), JSON.stringify(progress));
  } catch {
    // Storage unavailable (private browsing, quota) — the session still works in-memory for this
    // page load, it just won't resume after a reload. Not fatal.
  }
}

/**
 * `docs/product/customer-review-workflow.md`. Sequences the already-real `FeedbackForm`/
 * `FindingFeedback` API (`TASK-035`) one finding at a time — it does not duplicate that capture
 * contract, only adds the queue around it (§0). No `review_session` persistence object exists
 * (§8, deliberately) — session identity is free text and resume-after-interruption (§6) is
 * implemented with `localStorage`, not a backend change.
 */
export function ReviewSessionView() {
  const [auth, setAuth] = useState<AuthState>("loading");
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [reviewSession, setReviewSession] = useState<string | null>(null);
  const [sessionNameDraft, setSessionNameDraft] = useState(() =>
    typeof window === "undefined" ? "" : (window.localStorage.getItem(LAST_SESSION_NAME_KEY) ?? ""),
  );
  const [progress, setProgress] = useState<Progress>({ savedIds: [], skippedIds: [] });
  // Snapshot of `progress` as loaded at session start — used only to compute the initial queue
  // (resume-after-interruption). Deliberately never updated after that; `progress` itself is what
  // changes live as the session proceeds. See the `queue` useMemo below.
  const [sessionStartProgress, setSessionStartProgress] = useState<Progress>({
    savedIds: [],
    skippedIds: [],
  });
  const [index, setIndex] = useState(0);

  useEffect(() => {
    getCurrentUser()
      .then(() => setAuth("authenticated"))
      .catch(() => setAuth("anonymous"));
  }, []);

  useEffect(() => {
    if (!reviewSession) return;
    let cancelled = false;
    listFindings()
      .then((findings) => {
        if (!cancelled) setResult({ attempt, findings });
      })
      .catch((error: unknown) => {
        if (!cancelled) setResult({ attempt, error });
      });
    return () => {
      cancelled = true;
    };
  }, [reviewSession, attempt]);

  const retry = () => setAttempt((current) => current + 1);

  const startSession = useCallback(() => {
    const name = sessionNameDraft.trim();
    if (!name) return;
    window.localStorage.setItem(LAST_SESSION_NAME_KEY, name);
    const loaded = loadProgress(name);
    setProgress(loaded);
    setSessionStartProgress(loaded);
    setReviewSession(name);
  }, [sessionNameDraft]);

  // Filtered against `sessionStartProgress` — the snapshot taken once at session start, not the
  // live-updating `progress` state — or advancing mid-session would shift this array under
  // `index` and skip the next finding (filter one out, increment index, land two ahead instead
  // of one). `sessionStartProgress` only ever changes once (at `startSession`), so this is both
  // correct and stable for the rest of the live session.
  const queue = useMemo(() => {
    if (result === null || result.attempt !== attempt || "error" in result) return [];
    const handled = new Set([...sessionStartProgress.savedIds, ...sessionStartProgress.skippedIds]);
    return sortFindings(result.findings, "exposure").filter((finding) => !handled.has(finding.id));
  }, [result, attempt, sessionStartProgress]);

  const advance = useCallback(
    (outcome: "saved" | "skipped") => {
      const finding = queue[index];
      if (!finding || !reviewSession) return;
      const next: Progress = {
        savedIds: outcome === "saved" ? [...progress.savedIds, finding.id] : progress.savedIds,
        skippedIds:
          outcome === "skipped" ? [...progress.skippedIds, finding.id] : progress.skippedIds,
      };
      setProgress(next);
      saveProgress(reviewSession, next);
      setIndex((current) => current + 1);
    },
    [index, progress, queue, reviewSession],
  );

  if (auth === "loading") {
    return <LoadingState label="Loading review session…" />;
  }

  if (auth === "anonymous") {
    return (
      <ErrorState
        title="Log in to start a review session"
        message="Recording customer feedback requires an identified reviewer."
        retryHref="/login?next=%2Ffindings%2Freview"
      />
    );
  }

  if (!reviewSession) {
    return (
      <div className="reviewSession-start">
        <div className="findingDetail-header">
          <h1>Start a review session</h1>
        </div>
        <label className="loginForm-field">
          <span>Review session (company + date, e.g. acme-2026-08-19)</span>
          <input
            type="text"
            value={sessionNameDraft}
            onChange={(event) => setSessionNameDraft(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="loginForm-submit"
          disabled={sessionNameDraft.trim() === ""}
          onClick={startSession}
        >
          Start session
        </button>
      </div>
    );
  }

  if (result === null || result.attempt !== attempt) {
    return <LoadingState label="Loading findings…" />;
  }

  if ("error" in result) {
    const { message, requestId } = toErrorDisplay(result.error);
    return (
      <ErrorState title="Could not load findings" message={message} requestId={requestId} onRetry={retry} />
    );
  }

  if (queue.length === 0) {
    return (
      <EmptyState
        title="No findings left to review in this session."
        description="Every active finding has already been reviewed or skipped under this review session name."
      />
    );
  }

  if (index >= queue.length) {
    return (
      <div className="reviewSession-complete">
        <h1>Session complete</h1>
        <p>
          {progress.savedIds.length} reviewed, {progress.skippedIds.length} skipped this session.
        </p>
        <p className="findingDetail-meta">
          This is a record of what was captured, not a verdict — see `docs/product/
          customer-review-workflow.md` §4.
        </p>
        <Link href="/findings" className="findingDetail-back">
          ← Back to findings
        </Link>
      </div>
    );
  }

  const finding = queue[index];

  return (
    <article className="findingDetail reviewSession">
      <div className="reviewSession-progress">
        <span>
          Finding {index + 1} of {queue.length}
        </span>
        <span className="findingDetail-meta">Session: {reviewSession}</span>
      </div>

      <header className="findingDetail-header">
        <h1>{finding.title}</h1>
        <div className="findingDetail-headerPills">
          <EvidencePill level={finding.evidence_level} />
          <ReadinessPill readiness={finding.policy_readiness} />
          <WarningBadge count={finding.evidence.warnings.length} />
        </div>
      </header>

      <FindingCoreContent finding={finding} />

      <section className="findingDetail-section">
        <h2>Capture feedback</h2>
        <ReviewQueueForm
          key={finding.id}
          findingId={finding.id}
          reviewSession={reviewSession}
          onAdvance={() => advance("saved")}
          onSkip={() => advance("skipped")}
          onBack={() => setIndex((current) => Math.max(0, current - 1))}
          canGoBack={index > 0}
        />
      </section>
    </article>
  );
}
