import { CoverageChart, HistogramChart, StackedShares } from "@/components/charts";
import { Card, Notice } from "@/components/ui";
import { count, magnitude, percent, points } from "@/lib/format";
import type { UncertaintyPayload } from "@/lib/types";

const COMPONENT_ORDER = ["sampling", "house", "race", "cycle", "mean_parameter"];

export function UncertaintyPanel({ payload }: { payload: UncertaintyPayload }) {
  const loco = payload.backtest.filter(
    (row) => row.protocol === "leave_one_cycle_out" && row.estimand === "unweighted" && row.cycle !== "all",
  );
  const locoAll = payload.backtest.find(
    (row) => row.protocol === "leave_one_cycle_out" && row.estimand === "unweighted" && row.cycle === "all",
  );
  const forward = payload.backtest.filter(
    (row) => row.protocol === "forward_chain" && row.estimand === "unweighted" && row.cycle !== "all",
  );
  const heldOut2020 = loco.find((row) => row.cycle === "2020");
  const cycleSensitivity = payload.prior_sensitivity.filter((row) => row.parameter === "sd_cycle");
  const designs = payload.designs;
  const varianceGroups = designs.map((design) => {
    const parts = payload.variance_unweighted
      .filter((row) => row.design === design.design)
      .slice()
      .sort((a, b) => COMPONENT_ORDER.indexOf(a.component) - COMPONENT_ORDER.indexOf(b.component));
    return {
      label: design.label,
      predictiveSd: parts[0]?.predictive_sd ?? design.sd,
      parts: parts.map((part) => ({
        key: part.component,
        label: part.component_label,
        share: part.share,
      })),
    };
  });

  return (
    <div className="space-y-4">
      <Notice>{payload.simulation_note}</Notice>
      <div className="grid gap-4 lg:grid-cols-3">
        {designs.map((design) => (
          <Card key={design.design}>
            <h3 className="font-serif text-xl leading-tight">{design.label}</h3>
            <p className="mt-1 text-sm text-muted">
              SD {magnitude(design.sd, 2)} · median {points(design.p50)}
            </p>
            <HistogramChart histogram={design.histogram} mean={design.mean} height={150} />
            <p className="mt-2 text-xs leading-relaxed text-muted">
              95% interval {points(design.p025)} to {points(design.p975)}. Outside −24 to +24:{" "}
              {count(design.histogram.underflow)} below, {count(design.histogram.overflow)} above.{" "}
              {count(design.n_draws)} draws.
            </p>
          </Card>
        ))}
      </div>
      <Card>
        <h3 className="font-serif text-xl">Where the predictive variance sits</h3>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          Shares are the unweighted-average decomposition in variance_decomposition.csv. The SD printed
          at the right is that decomposition&apos;s predictive standard deviation, which is close to, and
          not identical to, the standard deviation of the Monte Carlo draws above.
        </p>
        <div className="mt-3">
          <StackedShares groups={varianceGroups} />
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          <li><Swatch color="#c4b49a" /> Sampling</li>
          <li><Swatch color="#8d4e2f" /> Pollster within race</li>
          <li><Swatch color="#1d4e89" /> Race</li>
          <li><Swatch color="#3f6f5b" /> Cycle</li>
          <li><Swatch color="#5e584e" /> Uncertainty in the mean</li>
        </ul>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h3 className="font-serif text-xl">Leave-one-cycle-out coverage</h3>
          <p className="mt-1 text-sm text-muted">
            Unweighted contest averages. Dashed lines are the nominal 50, 80, and 95 percent rates.
            {locoAll
              ? ` Across ${count(locoAll.n_races)} contests, 95% coverage is ${percent(locoAll.coverage_95)} and the mean PIT is ${locoAll.mean_pit.toFixed(2)}.`
              : ""}
          </p>
          <CoverageChart
            groups={loco.map((row) => ({
              label: row.cycle,
              coverage50: row.coverage_50,
              coverage80: row.coverage_80,
              coverage95: row.coverage_95,
            }))}
          />
          <p className="mt-2 text-xs text-muted">
            <Swatch color="#c4b8a5" /> 50% interval · <Swatch color="#1d4e89" /> 80% ·{" "}
            <Swatch color="#8d4e2f" /> 95%
          </p>
          {heldOut2020 ? (
            <p className="mt-3 text-sm leading-relaxed text-ink">
              Held-out 2020: mean actual error {points(heldOut2020.mean_actual_error)}, mean predicted
              median {points(heldOut2020.mean_predicted_median)}, 80% coverage{" "}
              {percent(heldOut2020.coverage_80)}, mean 95% width {heldOut2020.mean_width_95.toFixed(1)} points.
            </p>
          ) : null}
        </Card>
        <Card>
          <h3 className="font-serif text-xl">Forward chain</h3>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            Each cycle is scored with a model fit only on earlier cycles in this file. 2018 has no
            earlier cycle, so it has no forward-chain score.
          </p>
          <table className="mt-4 w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-1 font-medium">Cycle</th>
                <th className="py-1 font-medium">95% cov.</th>
                <th className="py-1 font-medium">Width</th>
                <th className="py-1 font-medium">Actual</th>
                <th className="py-1 font-medium">Predicted</th>
              </tr>
            </thead>
            <tbody>
              {forward.map((row) => (
                <tr key={row.cycle} className="border-t border-line">
                  <td className="py-1.5">{row.cycle}</td>
                  <td>{percent(row.coverage_95)}</td>
                  <td>{row.mean_width_95.toFixed(1)}</td>
                  <td>{points(row.mean_actual_error, 1)}</td>
                  <td>{points(row.mean_predicted_median, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 className="mt-6 font-serif text-xl">Cycle standard deviation and the prior</h3>
          <p className="mt-1 text-sm text-muted">
            Posterior median of the cycle standard deviation at three half-Cauchy scales. The other
            scale parameters move less; the full sensitivity table is in the API payload.
          </p>
          <ul className="mt-3 space-y-1 text-sm">
            {cycleSensitivity.map((row) => (
              <li key={row.half_cauchy_scale} className="flex justify-between border-t border-line py-1">
                <span>Scale {row.half_cauchy_scale}</span>
                <span>
                  {magnitude(row.p50, 2)}{" "}
                  <span className="text-muted">
                    ({magnitude(row.p05, 2)} to {magnitude(row.p95, 2)})
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <Card>
        <h3 className="font-serif text-xl">Posterior summaries</h3>
        <p className="mt-1 text-sm text-muted">
          {count(payload.sampler.draws)} retained draws after {count(payload.sampler.burn_in)} burn-in
          iterations, thin {payload.sampler.thin}, seed {payload.sampler.seed}. Median sample size in the
          modeled polls: {count(payload.preparation.median_sample_size)}. Median sampling variance:{" "}
          {payload.preparation.median_sampling_variance.toFixed(2)}.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-1 font-medium">Parameter</th>
                <th className="py-1 font-medium">Median</th>
                <th className="py-1 font-medium">5th</th>
                <th className="py-1 font-medium">95th</th>
                <th className="py-1 font-medium">ESS</th>
              </tr>
            </thead>
            <tbody>
              {payload.posterior.map((row) => (
                <tr key={row.parameter} className="border-t border-line">
                  <td className="py-1.5">
                    {row.label} <span className="text-muted">({row.unit})</span>
                  </td>
                  <td>{formatParameter(row.p50, row.unit, row.parameter)}</td>
                  <td>{formatParameter(row.p05, row.unit, row.parameter)}</td>
                  <td>{formatParameter(row.p95, row.unit, row.parameter)}</td>
                  <td>{row.ess.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function formatParameter(value: number, unit: string, parameter: string): string {
  if (unit === "multiplier" || parameter.startsWith("sd_")) return magnitude(value);
  return points(value);
}

function Swatch({ color }: { color: string }) {
  return (
    <span
      className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-middle"
      style={{ background: color }}
    />
  );
}
