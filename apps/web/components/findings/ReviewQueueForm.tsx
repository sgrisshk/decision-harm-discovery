"use client";

import { useCallback, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { submitFindingFeedback } from "@/lib/api/findings";
import type {
  FeedbackActionability,
  FeedbackCertainty,
  FeedbackCommitmentStrength,
  FeedbackCreatePayload,
  FeedbackNovelty,
  FeedbackTag,
} from "@/lib/api/types";
import {
  FEEDBACK_ACTIONABILITY_LABELS,
  FEEDBACK_CERTAINTY_LABELS,
  FEEDBACK_COMMITMENT_LABELS,
  FEEDBACK_NOVELTY_LABELS,
  FEEDBACK_TAG_LABELS,
} from "@/lib/copy/findingLanguage";

const NOVELTY_VALUES = Object.keys(FEEDBACK_NOVELTY_LABELS) as FeedbackNovelty[];
const ACTIONABILITY_VALUES = Object.keys(FEEDBACK_ACTIONABILITY_LABELS) as FeedbackActionability[];
const TAG_VALUES = Object.keys(FEEDBACK_TAG_LABELS) as FeedbackTag[];
const CERTAINTY_VALUES = Object.keys(FEEDBACK_CERTAINTY_LABELS) as FeedbackCertainty[];
const COMMITMENT_VALUES = Object.keys(FEEDBACK_COMMITMENT_LABELS) as FeedbackCommitmentStrength[];

const EMPTY_FORM = {
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

function hasContent(form: typeof EMPTY_FORM): boolean {
  return (
    form.novelty !== null ||
    form.actionability !== null ||
    form.tags.length > 0 ||
    form.customerComment.trim() !== "" ||
    form.customerCertainty !== null ||
    form.intendedAction.trim() !== "" ||
    form.commitmentStrength !== null ||
    form.customerOwner.trim() !== "" ||
    form.internalFollowUpOwner.trim() !== "" ||
    form.followUpDate !== ""
  );
}

/**
 * The capture half of the review queue (`TASK-036`, `docs/product/customer-review-workflow.md`
 * §2/§3) — same field set and `WRONG ⇒ comment` rule as `FeedbackForm.tsx` (the ad hoc,
 * single-finding capture form on the finding detail page), but Save-and-next/Skip/Back instead of
 * a persistent submit-and-show-history flow, since the queue's whole point is sequencing through
 * many findings, not remaining on one. Callers should render this with `key={findingId}` so
 * advancing to a new finding remounts it with a clean form, rather than needing an explicit reset.
 */
export function ReviewQueueForm({
  findingId,
  reviewSession,
  onAdvance,
  onSkip,
  onBack,
  canGoBack,
}: {
  findingId: string;
  reviewSession: string;
  /** Called after a successful save (or immediately, if the form had no content to save). */
  onAdvance: () => void;
  onSkip: () => void;
  onBack: () => void;
  canGoBack: boolean;
}) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wrongRequiresComment = form.tags.includes("WRONG") && form.customerComment.trim() === "";

  const toggleTag = useCallback((tag: FeedbackTag) => {
    setForm((prev) => ({
      ...prev,
      tags: prev.tags.includes(tag) ? prev.tags.filter((t) => t !== tag) : [...prev.tags, tag],
    }));
  }, []);

  const saveAndNext = useCallback(() => {
    if (wrongRequiresComment) {
      return;
    }
    // §3: a record is only created if at least one field was actually set — advancing past a
    // finding with the entire form untouched must not create an empty, meaningless row.
    if (!hasContent(form)) {
      onAdvance();
      return;
    }
    setSubmitting(true);
    setError(null);
    const payload: FeedbackCreatePayload = {
      review_session: reviewSession,
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
      .then(() => onAdvance())
      .catch((submitError: unknown) => {
        // A save failure must not silently advance — the reviewer stays on the current finding
        // with the error shown and their entered content preserved (§7).
        setError(
          submitError instanceof ApiError ? submitError.message : "An unexpected error occurred.",
        );
      })
      .finally(() => setSubmitting(false));
  }, [findingId, form, onAdvance, reviewSession, wrongRequiresComment]);

  return (
    <form
      className="feedbackForm reviewQueueForm"
      onSubmit={(event) => {
        event.preventDefault();
        saveAndNext();
      }}
    >
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
                setForm((prev) => ({ ...prev, novelty: prev.novelty === value ? null : value }))
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

      <div className="reviewQueueForm-actions">
        <button
          type="button"
          className="feedbackForm-submit reviewQueueForm-back"
          disabled={!canGoBack || submitting}
          onClick={onBack}
        >
          ← Back
        </button>
        <button
          type="button"
          className="feedbackForm-submit reviewQueueForm-skip"
          disabled={submitting}
          onClick={onSkip}
        >
          Skip
        </button>
        <button
          type="submit"
          className="feedbackForm-submit"
          disabled={submitting || wrongRequiresComment}
        >
          {submitting ? "Saving…" : "Save and next"}
        </button>
      </div>
    </form>
  );
}
