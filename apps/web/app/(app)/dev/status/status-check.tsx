"use client";

import { useCallback, useEffect, useState } from "react";
import { LoadingState } from "@/components/states";
import { getApiBaseUrl } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { getHealth, getReadiness } from "@/lib/api/health";
import type { HealthStatus } from "@/lib/api/types";

type CheckResult =
  | { state: "loading" }
  | { state: "ok"; status: string }
  | { state: "error"; message: string; status?: number; requestId?: string };

function useCheck(run: () => Promise<HealthStatus>): [CheckResult, () => void] {
  const [result, setResult] = useState<CheckResult>({ state: "loading" });

  // Split in two so the effect only ever calls a function whose setState
  // calls happen inside async callbacks, not synchronously in the effect
  // body (react-hooks/set-state-in-effect). `retry` is only ever called
  // from an event handler, where a synchronous reset-to-loading is fine.
  const runCheck = useCallback(() => {
    run()
      .then((response) => setResult({ state: "ok", status: response.status }))
      .catch((error: unknown) => {
        if (error instanceof ApiError) {
          setResult({
            state: "error",
            message: error.message,
            status: error.status,
            requestId: error.requestId,
          });
        } else {
          setResult({ state: "error", message: "An unexpected error occurred." });
        }
      });
  }, [run]);

  useEffect(() => {
    runCheck();
  }, [runCheck]);

  const retry = useCallback(() => {
    setResult({ state: "loading" });
    runCheck();
  }, [runCheck]);

  return [result, retry];
}

export function StatusCheck() {
  const [health, checkHealth] = useCheck(getHealth);
  const [ready, checkReady] = useCheck(getReadiness);
  const baseUrl = getApiBaseUrl();

  return (
    <div className="devStatusGrid">
      <StatusRow label={`GET ${baseUrl}/health`} result={health} onRetry={checkHealth} />
      <StatusRow label={`GET ${baseUrl}/ready`} result={ready} onRetry={checkReady} />
    </div>
  );
}

function StatusRow({
  label,
  result,
  onRetry,
}: {
  label: string;
  result: CheckResult;
  onRetry: () => void;
}) {
  return (
    <div className="devStatusRow">
      <span>{label}</span>
      {result.state === "loading" && <LoadingState label="Checking…" />}
      {result.state === "ok" && <span className="devStatusValue--ok">{result.status}</span>}
      {result.state === "error" && (
        <span className="devStatusValue--fail">
          {result.status ? `${result.status} ` : ""}
          {result.message}
          {result.requestId ? ` (${result.requestId})` : ""}
        </span>
      )}
      <button type="button" className="stateBlock-retry" onClick={onRetry}>
        Check again
      </button>
    </div>
  );
}
