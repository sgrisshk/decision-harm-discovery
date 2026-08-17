import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExposureFigure } from "./ExposureFigure";
import type { EffectEstimate } from "@/lib/api/types";

function estimate(overrides: Partial<EffectEstimate> = {}): EffectEstimate {
  return {
    value: 500,
    ci_low: 400,
    ci_high: 600,
    confidence_level: 0.95,
    method: "test",
    unit: "EUR per booking",
    ...overrides,
  };
}

describe("ExposureFigure", () => {
  it("renders a range, never a bare point estimate", () => {
    render(<ExposureFigure estimate={estimate()} />);
    expect(screen.getByText(/400–600/)).toBeInTheDocument();
    expect(screen.queryByText("500")).not.toBeInTheDocument();
  });

  it("shows 'no measurable economic effect' when the interval does not exclude zero", () => {
    render(<ExposureFigure estimate={estimate({ ci_low: -50, ci_high: 600 })} />);
    expect(screen.getByText("No measurable economic effect")).toBeInTheDocument();
    expect(screen.queryByText(/–/)).not.toBeInTheDocument();
  });

  it("treats a zero lower bound as not excluding zero", () => {
    render(<ExposureFigure estimate={estimate({ ci_low: 0 })} />);
    expect(screen.getByText("No measurable economic effect")).toBeInTheDocument();
  });

  it("always shows the exposure framing label", () => {
    render(<ExposureFigure estimate={estimate()} />);
    expect(screen.getByText("exposure")).toBeInTheDocument();
  });
});
