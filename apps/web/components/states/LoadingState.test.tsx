import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LoadingState } from "./LoadingState";

describe("LoadingState", () => {
  it("announces itself via role=status and aria-live=polite", () => {
    render(<LoadingState />);

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Loading…");
  });

  it("renders a custom label", () => {
    render(<LoadingState label="Loading findings…" />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading findings…");
  });
});
