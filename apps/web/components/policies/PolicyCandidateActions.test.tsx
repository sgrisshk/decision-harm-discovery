import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PolicyCandidateActions } from "./PolicyCandidateActions";

const originalFetch = global.fetch;

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.unstubAllEnvs();
});

const draftCandidate = {
  id: "cand-1",
  status: "DRAFT" as const,
  action_detail: null,
  rejection_reason: null,
  retirement_reason: null,
  blocked_by_source_lifecycle: false,
};

describe("PolicyCandidateActions", () => {
  it("disables submit-for-review until action_detail is entered", () => {
    render(<PolicyCandidateActions candidate={draftCandidate} />);
    expect(screen.getByRole("button", { name: "Submit for review" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Action (required, human-authored)"), {
      target: { value: "Require a second manager approval." },
    });
    expect(screen.getByRole("button", { name: "Submit for review" })).toBeEnabled();
  });

  it("submits for review and shows the approve/reject actions afterward", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ...draftCandidate,
          status: "UNDER_REVIEW",
          action_detail: "Require a second manager approval.",
        }),
        { status: 200 },
      ),
    );
    render(<PolicyCandidateActions candidate={draftCandidate} />);

    fireEvent.change(screen.getByLabelText("Action (required, human-authored)"), {
      target: { value: "Require a second manager approval." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit for review" }));

    expect(await screen.findByRole("button", { name: "Approve for shadow" })).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      "http://api.test/api/v1/policy-candidates/cand-1/transition",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows a blocked message instead of actions when blocked_by_source_lifecycle is true", () => {
    render(
      <PolicyCandidateActions candidate={{ ...draftCandidate, blocked_by_source_lifecycle: true }} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("blocked from advancing");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("requires a reason before rejecting an under-review candidate", async () => {
    const underReview = { ...draftCandidate, status: "UNDER_REVIEW" as const };
    render(<PolicyCandidateActions candidate={underReview} />);

    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Rejection reason (required to reject)"), {
      target: { value: "Customer has no operational lever." },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled(),
    );
  });
});
