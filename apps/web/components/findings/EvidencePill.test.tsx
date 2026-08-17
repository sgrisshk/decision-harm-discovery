import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvidencePill } from "./EvidencePill";

describe("EvidencePill", () => {
  it("renders the plain-language label, never the raw enum value", () => {
    render(<EvidencePill level="adjusted_observational_association" />);
    expect(screen.getByText("Holds after adjustment")).toBeInTheDocument();
    expect(screen.queryByText("adjusted_observational_association")).not.toBeInTheDocument();
  });

  it("maps every evidence level to a distinct label", () => {
    const levels = [
      "descriptive_observation",
      "predictive_association",
      "adjusted_observational_association",
      "quasi_causal_evidence",
      "experimental_evidence",
    ] as const;
    const labels = new Set<string>();
    for (const level of levels) {
      const { unmount, container } = render(<EvidencePill level={level} />);
      labels.add(container.textContent ?? "");
      unmount();
    }
    expect(labels.size).toBe(levels.length);
  });
});
