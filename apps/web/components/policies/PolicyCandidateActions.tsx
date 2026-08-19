"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { transitionPolicyCandidate } from "@/lib/api/policyCandidates";
import { ApiError } from "@/lib/api/errors";
import type { PolicyCandidate, PolicyCandidateStatus } from "@/lib/api/types";

type CandidateSnapshot = Pick<
  PolicyCandidate,
  | "id"
  | "status"
  | "action_detail"
  | "rejection_reason"
  | "retirement_reason"
  | "blocked_by_source_lifecycle"
>;

/**
 * The status-transition half of the Policy Candidate detail screen (`TASK-034`) — everything
 * `docs/product/policy-candidate-domain-model.md` §8 requires before a candidate is even eligible
 * for a backtest (`APPROVED_SHADOW`+, `docs/product/policy-backtest-screen.md` §1). Server-side
 * enforcement is the real guard (`app.policies.service.transition_policy_candidate`) — this
 * component only disables what's already illegal so a reviewer isn't surprised by a 409.
 */
export function PolicyCandidateActions({ candidate }: { candidate: CandidateSnapshot }) {
  const [state, setState] = useState<CandidateSnapshot>(candidate);
  const [actionDetailDraft, setActionDetailDraft] = useState("");
  const [reasonDraft, setReasonDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const transition = useCallback(
    (newStatus: PolicyCandidateStatus, options: { reason?: string; actionDetail?: string } = {}) => {
      setPending(true);
      setError(null);
      transitionPolicyCandidate(state.id, {
        new_status: newStatus,
        reason: options.reason || null,
        action_detail: options.actionDetail || null,
      })
        .then((updated) => setState(updated))
        .catch((err: unknown) => {
          setError(err instanceof ApiError ? err.message : "An unexpected error occurred.");
        })
        .finally(() => setPending(false));
    },
    [state.id],
  );

  if (state.blocked_by_source_lifecycle) {
    return (
      <div className="policyCandidateActions policyCandidateActions--blocked" role="status">
        <p>
          This candidate is blocked from advancing — its source finding is no longer active
          (§6). A human must review the change before it can move forward.
        </p>
      </div>
    );
  }

  return (
    <div className="policyCandidateActions">
      {state.status === "DRAFT" && (
        <div className="policyCandidateActions-group">
          <label className="policyCandidateActions-field">
            <span>Action (required, human-authored)</span>
            <textarea
              rows={2}
              placeholder="e.g. Require a second manager approval before applying the discount."
              value={actionDetailDraft}
              onChange={(event) => setActionDetailDraft(event.target.value)}
            />
          </label>
          <button
            type="button"
            className="policyCandidateActions-button"
            disabled={pending || actionDetailDraft.trim() === ""}
            onClick={() =>
              transition("UNDER_REVIEW", { actionDetail: actionDetailDraft.trim() })
            }
          >
            Submit for review
          </button>
        </div>
      )}

      {state.status === "UNDER_REVIEW" && (
        <div className="policyCandidateActions-group">
          <button
            type="button"
            className="policyCandidateActions-button"
            disabled={pending}
            onClick={() => transition("APPROVED_SHADOW")}
          >
            Approve for shadow
          </button>
          <label className="policyCandidateActions-field">
            <span>Rejection reason (required to reject)</span>
            <textarea
              rows={2}
              value={reasonDraft}
              onChange={(event) => setReasonDraft(event.target.value)}
            />
          </label>
          <button
            type="button"
            className="policyCandidateActions-button policyCandidateActions-button--secondary"
            disabled={pending || reasonDraft.trim() === ""}
            onClick={() => transition("REJECTED", { reason: reasonDraft.trim() })}
          >
            Reject
          </button>
        </div>
      )}

      {(state.status === "APPROVED_SHADOW" || state.status === "APPROVED_FOR_CUSTOMER_DECISION") && (
        <div className="policyCandidateActions-group">
          <Link
            className="policyCandidateActions-button"
            href={`/policy-candidates/backtest?id=${state.id}`}
          >
            Run historical backtest
          </Link>
        </div>
      )}

      {state.status === "REJECTED" && (
        <p className="findingDetail-meta">Rejected: {state.rejection_reason}</p>
      )}
      {state.status === "RETIRED" && (
        <p className="findingDetail-meta">Retired: {state.retirement_reason}</p>
      )}

      {error && (
        <p className="policyCandidateActions-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
