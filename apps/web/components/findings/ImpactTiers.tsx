import { ExposureFigure } from "@/components/findings/ExposureFigure";
import { reportableTier1, reportableTier2 } from "@/lib/api/impact";
import { tierPopulationLabel, tierQuantityLabel } from "@/lib/copy/findingLanguage";
import type { CandidateExposureTier, FindingImpact } from "@/lib/api/types";

/**
 * `FindingImpactRead`'s "money at stake" tiers (`TASK-088`/`TASK-090`).
 * Shared by `FindingCoreContent` (findings) and `PolicyCandidateDetailView`
 * (policy candidates, whose `expected_benefit_snapshot` is the same
 * `FindingImpact` shape) so both screens render one definition, never two
 * copies that can drift apart.
 *
 * Renders only what `impact.reportable_tiers` actually clears — a tier
 * object being present and non-null on the payload is not sufficient by
 * itself. Tier 1 (population `E`) is always the primary headline figure when
 * reportable; tier 2 (population `E_dev`, strictly narrower) is shown as a
 * clearly-labeled secondary figure, never summed or blended with tier 1
 * (`docs/product/finding-product-contract.md` §3: "never add two findings'
 * `historical_impact`" — the same discipline applies here to two tiers of
 * one finding). `attributable_impact` (tier 3) is always absent in this
 * project's real history today; rendered defensively, with no elaborate UI
 * for a slot that has never once been populated.
 */
export function ImpactTiers({ impact }: { impact: FindingImpact }) {
  const tier1 = reportableTier1(impact);
  const tier2 = reportableTier2(impact);

  if (!tier1 && !tier2) {
    return <p className="findingDetail-meta">No reportable exposure figure yet.</p>;
  }

  return (
    <>
      {tier1 && <TierFigure tier={tier1} primary />}
      {tier2 && <TierFigure tier={tier2} primary={!tier1} />}
      {impact.attributable_impact && (
        <p className="findingDetail-meta">
          Attributable harmful impact ({tierPopulationLabel(impact.attributable_impact.population_scope)}
          ): <ExposureFigure estimate={impact.attributable_impact.attributable_impact} />
        </p>
      )}
    </>
  );
}

function TierFigure({ tier, primary }: { tier: CandidateExposureTier; primary: boolean }) {
  return (
    <div
      className={
        primary ? "findingDetail-exposureHeadline" : "findingDetail-exposureSecondary"
      }
    >
      <p>
        <ExposureFigure estimate={tier.candidate_exposure} />{" "}
        <span className="findingDetail-meta">
          {tierQuantityLabel(tier)} — {tier.outcome_name}, {tierPopulationLabel(tier.population_scope)}
          {" ("}
          {tier.affected_records.toLocaleString("en-US")} records)
        </span>
      </p>
      {tier.annualization_justified && tier.annualized_candidate_exposure ? (
        <p>
          Annualized estimate: <ExposureFigure estimate={tier.annualized_candidate_exposure} />
        </p>
      ) : (
        <p className="findingDetail-meta">Not enough history to project forward.</p>
      )}
    </div>
  );
}
