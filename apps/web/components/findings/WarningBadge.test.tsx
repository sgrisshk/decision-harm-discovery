import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WarningBadge } from "./WarningBadge";

describe("WarningBadge", () => {
  it("renders nothing when count is zero", () => {
    const { container } = render(<WarningBadge count={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("pluralizes correctly", () => {
    render(<WarningBadge count={1} />);
    expect(screen.getByText("⚠ 1 caveat")).toBeInTheDocument();
  });

  it("shows the count for multiple caveats", () => {
    render(<WarningBadge count={3} />);
    expect(screen.getByText("⚠ 3 caveats")).toBeInTheDocument();
  });
});
