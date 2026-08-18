import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackForm } from "./FeedbackForm";

const originalFetch = global.fetch;

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.unstubAllEnvs();
});

function anonymousMeResponse() {
  return new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 });
}

function authenticatedMeResponse() {
  return new Response(
    JSON.stringify({ id: "user-1", email: "reviewer@example.com", display_name: "Reviewer" }),
    { status: 200 },
  );
}

describe("FeedbackForm", () => {
  it("shows a login prompt instead of the form when nobody is authenticated", async () => {
    global.fetch = vi.fn().mockResolvedValue(anonymousMeResponse());
    render(<FeedbackForm findingId="finding-1" initialHistory={[]} />);

    const link = await screen.findByRole("link", { name: "Log in" });
    expect(link).toHaveAttribute("href", "/login?next=%2Ffindings%2Ffinding-1");
    expect(screen.queryByRole("button", { name: "Record feedback" })).not.toBeInTheDocument();
  });

  it("disables submit when the WRONG tag is set without a comment", async () => {
    global.fetch = vi.fn().mockResolvedValue(authenticatedMeResponse());
    render(<FeedbackForm findingId="finding-1" initialHistory={[]} />);

    fireEvent.change(await screen.findByLabelText("Review session"), {
      target: { value: "acme-2026-08-18" },
    });
    expect(screen.getByRole("button", { name: "Record feedback" })).toBeEnabled();

    fireEvent.click(screen.getByLabelText("Doesn't look right"));
    expect(screen.getByRole("button", { name: "Record feedback" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("What's wrong? (required)"), {
      target: { value: "We don't have this policy." },
    });
    expect(screen.getByRole("button", { name: "Record feedback" })).toBeEnabled();
  });

  it("submits feedback and prepends it to the history list", async () => {
    const created = {
      id: "feedback-1",
      finding_id: "finding-1",
      created_by_user_id: "user-1",
      review_session: "acme-2026-08-18",
      captured_at: "2026-08-18T00:00:00Z",
      novelty: "NEW",
      actionability: null,
      tags: [],
      customer_comment: null,
      customer_certainty: null,
      intended_action: null,
      commitment_strength: null,
      customer_owner: null,
      internal_follow_up_owner: null,
      follow_up_date: null,
      created_at: "2026-08-18T00:00:00Z",
    };
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(authenticatedMeResponse())
      .mockResolvedValueOnce(new Response(JSON.stringify(created), { status: 201 }));
    render(<FeedbackForm findingId="finding-1" initialHistory={[]} />);

    fireEvent.change(await screen.findByLabelText("Review session"), {
      target: { value: "acme-2026-08-18" },
    });
    fireEvent.click(screen.getByRole("button", { name: "New to us" }));
    fireEvent.click(screen.getByRole("button", { name: "Record feedback" }));

    await waitFor(() => expect(screen.getByText(/acme-2026-08-18/)).toBeInTheDocument());
    expect(global.fetch).toHaveBeenLastCalledWith(
      "http://api.test/api/v1/findings/finding-1/feedback",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
