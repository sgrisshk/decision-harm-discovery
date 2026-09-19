import { impactFramingLabel } from "@/lib/copy/findingLanguage";
import type { EffectEstimate } from "@/lib/api/types";

type ExposureFigureProps = {
  estimate: EffectEstimate;
};

/**
 * Renders any `EffectEstimate` (e.g. a tier's `candidate_exposure`/
 * `annualized_candidate_exposure`, `TASK-088`/`TASK-090`) as a range, never a
 * bare point estimate. docs/product/finding-product-contract.md §3: an
 * interval that does not exclude zero on the low side is not material and
 * must read as "no measurable economic effect," never as a number with a
 * footnote. Purely presentational and population-agnostic — callers are
 * responsible for labeling which population/tier the estimate belongs to.
 */
export function ExposureFigure({ estimate }: ExposureFigureProps) {
  if (estimate.ci_low <= 0) {
    return <span className="exposureFigure exposureFigure--none">No measurable economic effect</span>;
  }
  const formatted = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  return (
    <span className="exposureFigure">
      <span className="exposureFigure-label">{impactFramingLabel()}</span>
      {formatted.format(estimate.ci_low)}–{formatted.format(estimate.ci_high)} {estimate.unit.split(" ")[0]}
    </span>
  );
}
