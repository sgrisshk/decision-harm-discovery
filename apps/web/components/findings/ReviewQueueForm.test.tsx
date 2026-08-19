import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewQueueForm } from "./ReviewQueueForm";

const originalFetch = global.fetch;

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.unstubAllEnvs();
});

describe("ReviewQueueForm", () => {
  it("disables Back when canGoBack is false", () => {
    const onBack = vi.fn();
    render(
      <ReviewQueueForm
        findingId="finding-1"
        reviewSession="acme-2026-08-19"
        onAdvance={vi.fn()}
        onSkip={vi.fn()}
        onBack={onBack}
        canGoBack={false}
      />,
    );
    expect(screen.getByRole("button", { name: "← Back" })).toBeDisabled();
  });

  it("skip advances without any API call", () => {
    global.fetch = vi.fn();
    const onSkip = vi.fn();
    render(
      <ReviewQueueForm
        findingId="finding-1"
        reviewSession="acme-2026-08-19"
        onAdvance={vi.fn()}
        onSkip={onSkip}
        onBack={vi.fn()}
        canGoBack={true}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("save-and-next on an untouched form advances without any API call", () => {
    global.fetch = vi.fn();
    const onAdvance = vi.fn();
    render(
      <ReviewQueueForm
        findingId="finding-1"
        reviewSession="acme-2026-08-19"
        onAdvance={onAdvance}
        onSkip={vi.fn()}
        onBack={vi.fn()}
        canGoBack={true}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save and next" }));
    expect(onAdvance).toHaveBeenCalledTimes(1);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("disables save-and-next when WRONG is set without a comment", () => {
    render(
      <ReviewQueueForm
        findingId="finding-1"
        reviewSession="acme-2026-08-19"
        onAdvance={vi.fn()}
        onSkip={vi.fn()}
        onBack={vi.fn()}
        canGoBack={true}
      />,
    );
    fireEvent.click(screen.getByLabelText("Doesn't look right"));
    expect(screen.getByRole("button", { name: "Save and next" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("What's wrong? (required)"), {
      target: { value: "We don't have this policy." },
    });
    expect(screen.getByRole("button", { name: "Save and next" })).toBeEnabled();
  });

  it("save-and-next with real content posts feedback then advances", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "fb-1" }), { status: 201 }),
    );
    const onAdvance = vi.fn();
    render(
      <ReviewQueueForm
        findingId="finding-1"
        reviewSession="acme-2026-08-19"
        onAdvance={onAdvance}
        onSkip={vi.fn()}
        onBack={vi.fn()}
        canGoBack={true}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "New to us" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and next" }));

    await waitFor(() => expect(onAdvance).toHaveBeenCalledTimes(1));
    expect(global.fetch).toHaveBeenCalledWith(
      "http://api.test/api/v1/findings/finding-1/feedback",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
