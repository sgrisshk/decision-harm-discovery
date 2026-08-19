"use client";

import { useCallback, useState } from "react";
import { EmptyState } from "@/components/states";
import { ApiError } from "@/lib/api/errors";
import { transitionPolicyCandidate, triggerBacktest } from "@/lib/api/policyCandidates";
import type { PolicyBacktestRun, PolicyCandidateBacktestResult } from "@/lib/api/types";

const money = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/**
 * Full interactive half of `docs/product/policy-backtest-screen.md`: the trigger action (§2),
 * the result sections (§3/§4), and the collapsed run history (§6 "multiple runs... never silently
 * discarded"). One client component over server-fetched initial history, same pattern as
 * `FeedbackForm.tsx`.
 */
export function TriggerBacktestForm({
  candidateId,
  initialRuns,
}: {
  candidateId: string;
  initialRuns: PolicyBacktestRun[];
}) {
  const [runs, setRuns] = useState(initialRuns);
  const [costInput, setCostInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onTrigger = useCallback(() => {
    setPending(true);
    setError(null);
    const cost = costInput.trim() === "" ? null : Number(costInput);
    triggerBacktest(candidateId, cost)
      .then((run) => setRuns((prev) => [run, ...prev]))
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "An unexpected error occurred.");
      })
      .finally(() => setPending(false));
  }, [candidateId, costInput]);

  const latest = runs[0];
  const priorRuns = runs.slice(1);

  return (
    <div className="backtestPanel">
      <div className="backtestPanel-trigger">
        <label className="backtestPanel-costField">
          <span>Cost per review (EUR, optional)</span>
          <input
            type="number"
            min="0"
            step="0.01"
            value={costInput}
            onChange={(event) => setCostInput(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="backtestPanel-runButton"
          disabled={pending}
          onClick={onTrigger}
        >
          {pending ? "Running…" : "Run historical backtest"}
        </button>
        {error && (
          <p className="backtestPanel-error" role="alert">
            {error}
          </p>
        )}
      </div>

      {latest ? (
        <>
          <BacktestRunView run={latest} />
          {latest.status === "completed" && latest.backtest_result && (
            <NextActions candidateId={candidateId} result={latest.backtest_result} />
          )}
        </>
      ) : (
        <EmptyState
          title="No backtest has been run yet."
          description="This candidate's benefit is currently based on historical exposure only, not a forward-looking test."
        />
      )}

      {priorRuns.length > 0 && (
        <details className="backtestPanel-history">
          <summary>{priorRuns.length} earlier run(s)</summary>
          <div className="backtestPanel-historyList">
            {priorRuns.map((run) => (
              <BacktestRunView key={run.id} run={run} compact />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function BacktestRunView({ run, compact = false }: { run: PolicyBacktestRun; compact?: boolean }) {
  const meta = new Date(run.created_at).toLocaleString("en-US");
  if (run.status === "failed") {
    return (
      <div className="stateBlock stateBlock--error" role="alert">
        <p className="stateBlock-title">Backtest run failed ({meta})</p>
        <p>{run.failure_reason}</p>
      </div>
    );
  }
  if (!run.backtest_result) {
    return null;
  }
  return <BacktestResultView result={run.backtest_result} runAt={meta} compact={compact} />;
}

function BacktestResultView({
  result,
  runAt,
  compact,
}: {
  result: PolicyCandidateBacktestResult;
  runAt: string;
  compact: boolean;
}) {
  return (
    <div className="backtestResult">
      <p className="findingDetail-meta">Run {runAt} · against the future-holdout window</p>

      <div className="backtestResult-section">
        <p className="findingDetail-effectLabel">What it would have touched</p>
        <p>
          {result.affected_decisions.toLocaleString("en-US")} bookings in the future-holdout window
          would have matched the rule.
        </p>
      </div>

      <div className="backtestResult-section">
        <p className="findingDetail-effectLabel">Upside and downside — both, always</p>
        <p>Avoided bad outcomes: {result.avoided_bad_outcomes.toLocaleString("en-US")} bookings</p>
        <p className="findingDetail-meta">&ldquo;Bad&rdquo; = {result.bad_outcome_definition}</p>
        <p>
          Suppressed good outcomes: {result.suppressed_good_outcomes.toLocaleString("en-US")}{" "}
          bookings
        </p>
      </div>

      <div className="backtestResult-section">
        <p className="findingDetail-effectLabel">Benefit</p>
        <p className="findingDetail-effectValue">
          {money.format(result.benefit.value)} {result.benefit.unit.split(" ")[0]} (
          {money.format(result.benefit.ci_low)}–{money.format(result.benefit.ci_high)})
        </p>
        <p className="findingDetail-meta">
          {result.benefit_is_adjusted
            ? "Confounder-adjusted."
            : "Raw, unadjusted — an upper bound, not a confounder-controlled estimate."}
        </p>
      </div>

      {!compact && (
        <div className="backtestResult-section">
          <p className="findingDetail-effectLabel">Operational cost</p>
          {result.operational_cost ? (
            <p>
              {money.format(result.operational_cost.value)}{" "}
              {result.operational_cost.unit.split(" ")[0]}, assumed at €
              {result.operational_cost_per_review_eur}/review, not estimated from data.
            </p>
          ) : (
            <p className="findingDetail-meta">
              No cost assumption entered — net effect below is benefit only, not cost-netted.
            </p>
          )}
        </div>
      )}

      <div className="backtestResult-section">
        <p className="findingDetail-effectLabel">Net effect</p>
        {result.no_measurable_net_effect ? (
          <p>No measurable net effect.</p>
        ) : (
          <p className="findingDetail-effectValue">
            {money.format(result.net_effect.value)} {result.net_effect.unit.split(" ")[0]} (
            {money.format(result.net_effect.ci_low)}–{money.format(result.net_effect.ci_high)})
            {result.net_effect_is_cost_exclusive ? " — before operational cost" : " — net of cost"}
          </p>
        )}
        {!compact && <p className="findingDetail-disclaimer">{result.methodology_disclosure}</p>}
      </div>
    </div>
  );
}

/**
 * §7's gated next actions — which of the three is offered depends only on `no_measurable_net_effect`
 * and `net_effect`'s sign, never on a value this component invents. "Keep in shadow" is a no-op
 * (the candidate already is); the other two call the transition endpoint directly. This screen
 * never offers an "enforce" action, at any result (§9's absolute boundary).
 */
function NextActions({
  candidateId,
  result,
}: {
  candidateId: string;
  result: PolicyCandidateBacktestResult;
}) {
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const retire = useCallback(() => {
    setPending(true);
    setError(null);
    transitionPolicyCandidate(candidateId, { new_status: "RETIRED", reason: reason.trim() })
      .then(() => setMessage("Candidate retired."))
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "An unexpected error occurred.");
      })
      .finally(() => setPending(false));
  }, [candidateId, reason]);

  const proposeForCustomer = useCallback(() => {
    setPending(true);
    setError(null);
    transitionPolicyCandidate(candidateId, { new_status: "APPROVED_FOR_CUSTOMER_DECISION" })
      .then(() => setMessage("Proposed for customer decision."))
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "An unexpected error occurred.");
      })
      .finally(() => setPending(false));
  }, [candidateId]);

  if (message) {
    return <p className="findingDetail-meta">{message}</p>;
  }

  const negative = !result.no_measurable_net_effect && result.net_effect.value < 0;
  const positive = !result.no_measurable_net_effect && result.net_effect.value > 0;

  return (
    <div className="backtestPanel-nextActions">
      {result.no_measurable_net_effect && (
        <p className="findingDetail-meta">No measurable net effect — keep in shadow.</p>
      )}
      {negative && (
        <div className="policyCandidateActions-group">
          <label className="policyCandidateActions-field">
            <span>Retirement reason (required)</span>
            <textarea
              rows={2}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <button
            type="button"
            className="policyCandidateActions-button policyCandidateActions-button--secondary"
            disabled={pending || reason.trim() === ""}
            onClick={retire}
          >
            Retire this candidate
          </button>
        </div>
      )}
      {positive && (
        <button
          type="button"
          className="policyCandidateActions-button"
          disabled={pending}
          onClick={proposeForCustomer}
        >
          Propose for customer decision
        </button>
      )}
      {error && (
        <p className="backtestPanel-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
