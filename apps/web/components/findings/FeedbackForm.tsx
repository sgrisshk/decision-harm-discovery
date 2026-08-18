"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getCurrentUser } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/errors";
import { submitFindingFeedback } from "@/lib/api/findings";
import type {
  FeedbackActionability,
  FeedbackCertainty,
  FeedbackCommitmentStrength,
  FeedbackCreatePayload,
  FeedbackNovelty,
  FeedbackTag,
  FindingFeedback,
} from "@/lib/api/types";
import {
  FEEDBACK_ACTIONABILITY_LABELS,
  FEEDBACK_CERTAINTY_LABELS,
  FEEDBACK_COMMITMENT_LABELS,
  FEEDBACK_NOVELTY_LABELS,
  FEEDBACK_TAG_LABELS,
} from "@/lib/copy/findingLanguage";

type AuthState = "loading" | "anonymous" | "authenticated";

const NOVELTY_VALUES = Object.keys(FEEDBACK_NOVELTY_LABELS) as FeedbackNovelty[];
const ACTIONABILITY_VALUES = Object.keys(FEEDBACK_ACTIONABILITY_LABELS) as FeedbackActionability[];
const TAG_VALUES = Object.keys(FEEDBACK_TAG_LABELS) as FeedbackTag[];
const CERTAINTY_VALUES = Object.keys(FEEDBACK_CERTAINTY_LABELS) as FeedbackCertainty[];
const COMMITMENT_VALUES = Object.keys(FEEDBACK_COMMITMENT_LABELS) as FeedbackCommitmentStrength[];

const EMPTY_FORM = {
  reviewSession: "",
  novelty: null as FeedbackNovelty | null,
  actionability: null as FeedbackActionability | null,
  tags: [] as FeedbackTag[],
  customerComment: "",
  customerCertainty: null as FeedbackCertainty | null,
  intendedAction: "",
  commitmentStrength: null as FeedbackCommitmentStrength | null,
  customerOwner: "",
  internalFollowUpOwner: "",
  followUpDate: "",
};

/**
 * Real capture form for `TASK-035` (`docs/product/finding-feedback-contract.md`), replacing the
 * disabled chip-row placeholder from `TASK-027`. Requires an authenticated session (`TASK-053`) —
 * shows a login prompt instead of the form when anonymous.
 */
export function FeedbackForm({
  findingId,
  initialHistory,
}: {
  findingId: string;
  initialHistory: FindingFeedback[];
}) {
  const [auth, setAuth] = useState<AuthState>("loading");
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState(initialHistory);

  useEffect(() => {
    getCurrentUser()
      .then(() => setAuth("authenticated"))
      .catch(() => setAuth("anonymous"));
  }, []);

  const wrongRequiresComment = form.tags.includes("WRONG") && form.customerComment.trim() === "";
  const canSubmit = form.reviewSession.trim() !== "" && !wrongRequiresComment && !submitting;

  const toggleTag = useCallback((tag: FeedbackTag) => {
    setForm((prev) => ({
      ...prev,
      tags: prev.tags.includes(tag) ? prev.tags.filter((t) => t !== tag) : [...prev.tags, tag],
    }));
  }, []);

  const onSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!canSubmit) {
        return;
      }
      setSubmitting(true);
      setError(null);
      const payload: FeedbackCreatePayload = {
        review_session: form.reviewSession.trim(),
        novelty: form.novelty,
        actionability: form.actionability,
        tags: form.tags,
        customer_comment: form.customerComment.trim() || null,
        customer_certainty: form.customerCertainty,
        intended_action: form.intendedAction.trim() || null,
        commitment_strength: form.commitmentStrength,
        customer_owner: form.customerOwner.trim() || null,
        internal_follow_up_owner: form.internalFollowUpOwner.trim() || null,
        follow_up_date: form.followUpDate || null,
      };
      submitFindingFeedback(findingId, payload)
        .then((created) => {
          setHistory((prev) => [created, ...prev]);
          setForm(EMPTY_FORM);
        })
        .catch((submitError: unknown) => {
          setError(
            submitError instanceof ApiError
              ? submitError.message
              : "An unexpected error occurred.",
          );
        })
        .finally(() => setSubmitting(false));
    },
    [canSubmit, findingId, form],
  );

  const loginHref = useMemo(
    () => `/login?next=${encodeURIComponent(`/findings/${findingId}`)}`,
    [findingId],
  );

  return (
    <div className="findingDetail-feedback">
      {auth === "anonymous" && (
        <p className="feedbackForm-loginPrompt">
          <Link href={loginHref}>Log in</Link> to record customer feedback on this finding.
        </p>
      )}
      {auth === "authenticated" && (
        <form className="feedbackForm" onSubmit={onSubmit}>
          <label className="feedbackForm-field">
            <span>Review session</span>
            <input
              type="text"
              required
              placeholder="e.g. acme-2026-08-18"
              value={form.reviewSession}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, reviewSession: event.target.value }))
              }
            />
          </label>

          <div className="feedbackForm-group">
            <span className="feedbackForm-groupLabel">Novelty</span>
            <div className="feedbackForm-toggleRow">
              {NOVELTY_VALUES.map((value) => (
                <button
                  key={value}
                  type="button"
                  className="feedbackForm-toggle"
                  aria-pressed={form.novelty === value}
                  onClick={() =>
                    setForm((prev) => ({
                      ...prev,
                      novelty: prev.novelty === value ? null : value,
                    }))
                  }
                >
                  {FEEDBACK_NOVELTY_LABELS[value]}
                </button>
              ))}
            </div>
          </div>

          <div className="feedbackForm-group">
            <span className="feedbackForm-groupLabel">Actionability</span>
            <div className="feedbackForm-toggleRow">
              {ACTIONABILITY_VALUES.map((value) => (
                <button
                  key={value}
                  type="button"
                  className="feedbackForm-toggle"
                  aria-pressed={form.actionability === value}
                  onClick={() =>
                    setForm((prev) => ({
                      ...prev,
                      actionability: prev.actionability === value ? null : value,
                    }))
                  }
                >
                  {FEEDBACK_ACTIONABILITY_LABELS[value]}
                </button>
              ))}
            </div>
          </div>

          <div className="feedbackForm-group">
            <span className="feedbackForm-groupLabel">Tags</span>
            <div className="feedbackForm-checkboxRow">
              {TAG_VALUES.map((value) => (
                <label key={value}>
                  <input
                    type="checkbox"
                    checked={form.tags.includes(value)}
                    onChange={() => toggleTag(value)}
                  />
                  {FEEDBACK_TAG_LABELS[value]}
                </label>
              ))}
            </div>
          </div>

          {form.tags.includes("WRONG") && (
            <label className="feedbackForm-field">
              <span>What&apos;s wrong? (required)</span>
              <textarea
                required
                rows={3}
                value={form.customerComment}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, customerComment: event.target.value }))
                }
              />
            </label>
          )}

          <details className="feedbackForm-details">
            <summary>More detail (optional)</summary>
            <div className="feedbackForm">
              <div className="feedbackForm-group">
                <span className="feedbackForm-groupLabel">
                  Customer certainty (their own, not statistical confidence)
                </span>
                <div className="feedbackForm-toggleRow">
                  {CERTAINTY_VALUES.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className="feedbackForm-toggle"
                      aria-pressed={form.customerCertainty === value}
                      onClick={() =>
                        setForm((prev) => ({
                          ...prev,
                          customerCertainty: prev.customerCertainty === value ? null : value,
                        }))
                      }
                    >
                      {FEEDBACK_CERTAINTY_LABELS[value]}
                    </button>
                  ))}
                </div>
              </div>

              <label className="feedbackForm-field">
                <span>Intended action</span>
                <textarea
                  rows={2}
                  value={form.intendedAction}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, intendedAction: event.target.value }))
                  }
                />
              </label>

              <div className="feedbackForm-group">
                <span className="feedbackForm-groupLabel">Commitment strength</span>
                <div className="feedbackForm-toggleRow">
                  {COMMITMENT_VALUES.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className="feedbackForm-toggle"
                      aria-pressed={form.commitmentStrength === value}
                      onClick={() =>
                        setForm((prev) => ({
                          ...prev,
                          commitmentStrength: prev.commitmentStrength === value ? null : value,
                        }))
                      }
                    >
                      {FEEDBACK_COMMITMENT_LABELS[value]}
                    </button>
                  ))}
                </div>
              </div>

              <label className="feedbackForm-field">
                <span>Customer owner</span>
                <input
                  type="text"
                  value={form.customerOwner}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, customerOwner: event.target.value }))
                  }
                />
              </label>

              <label className="feedbackForm-field">
                <span>Internal follow-up owner</span>
                <input
                  type="text"
                  value={form.internalFollowUpOwner}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, internalFollowUpOwner: event.target.value }))
                  }
                />
              </label>

              <label className="feedbackForm-field">
                <span>Follow-up date</span>
                <input
                  type="date"
                  value={form.followUpDate}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, followUpDate: event.target.value }))
                  }
                />
              </label>
            </div>
          </details>

          {error && (
            <p className="feedbackForm-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="feedbackForm-submit" disabled={!canSubmit}>
            {submitting ? "Recording…" : "Record feedback"}
          </button>
        </form>
      )}

      {history.length > 0 && (
        <div className="feedbackForm-history">
          {history.map((entry) => (
            <FeedbackHistoryItem key={entry.id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}

function FeedbackHistoryItem({ entry }: { entry: FindingFeedback }) {
  const chips: string[] = [
    ...(entry.novelty ? [FEEDBACK_NOVELTY_LABELS[entry.novelty]] : []),
    ...(entry.actionability ? [FEEDBACK_ACTIONABILITY_LABELS[entry.actionability]] : []),
    ...entry.tags.map((tag) => FEEDBACK_TAG_LABELS[tag]),
  ];
  return (
    <div className="feedbackForm-historyItem">
      <p className="feedbackForm-historyMeta">
        {entry.review_session} · {new Date(entry.captured_at).toLocaleDateString("en-US")}
      </p>
      {chips.length > 0 && (
        <div className="findingDetail-feedbackChips">
          {chips.map((chip) => (
            <span key={chip} className="findingDetail-feedbackChip">
              {chip}
            </span>
          ))}
        </div>
      )}
      {entry.customer_comment && <p>{entry.customer_comment}</p>}
    </div>
  );
}
