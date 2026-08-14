import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders the title and optional description", () => {
    render(<EmptyState title="No datasets yet" description="Upload one to get started." />);

    expect(screen.getByText("No datasets yet")).toBeInTheDocument();
    expect(screen.getByText("Upload one to get started.")).toBeInTheDocument();
  });

  it("renders an optional action", () => {
    render(<EmptyState title="No findings yet" action={<button type="button">Refresh</button>} />);

    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });
});
