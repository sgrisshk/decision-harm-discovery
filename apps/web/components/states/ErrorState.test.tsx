import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorState } from "./ErrorState";

describe("ErrorState", () => {
  it("announces itself via role=alert and renders the message", () => {
    render(<ErrorState message="Could not reach the API." />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Something went wrong");
    expect(alert).toHaveTextContent("Could not reach the API.");
  });

  it("renders an optional request ID and retry link", () => {
    render(
      <ErrorState
        title="Could not load findings"
        message="Request failed with status 503."
        requestId="req-42"
        retryHref="/findings"
      />,
    );

    expect(screen.getByText(/req-42/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retry" })).toHaveAttribute("href", "/findings");
  });

  it("omits the retry link when no retryHref is given", () => {
    render(<ErrorState message="Unexpected error." />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
