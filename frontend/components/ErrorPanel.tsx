import { DivergingBars, HistogramChart } from "@/components/charts";
import { Card } from "@/components/ui";
import { count, magnitude, points } from "@/lib/format";
import type { ErrorsPayload } from "@/lib/types";

export function ErrorPanel({ payload }: { payload: ErrorsPayload }) {
  const outside = payload.histogram.underflow + payload.histogram.overflow;
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Card className="lg:col-span-3">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <h3 className="font-serif text-xl">Signed error</h3>
          <p className="text-sm text-muted">
            Mean {points(payload.poll_level.mean_signed_error)} · median{" "}
            {points(payload.poll_level.median_signed_error)}
          </p>
        </div>
        <HistogramChart histogram={payload.histogram} mean={payload.poll_level.mean_signed_error} />
        <p className="mt-2 text-xs leading-relaxed text-muted">
          Each bar is a 2-point bin of question-level signed error. Blue is a poll more Democratic
          than the two-candidate result. {count(payload.histogram.n)} questions. {count(outside)} sit
          outside −24 to +24 and are counted in the end totals ({count(payload.histogram.underflow)} below,{" "}
          {count(payload.histogram.overflow)} above). The dashed line is the mean.
        </p>
      </Card>
      <Card className="lg:col-span-2">
        <h3 className="font-serif text-xl">By election cycle</h3>
        <DivergingBars
          rows={payload.cycles.map((cycle) => ({
            label: String(cycle.cycle),
            value: cycle.mean_signed_error ?? 0,
            note: `${count(cycle.n_questions)}`,
          }))}
        />
        <table className="mt-2 w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="py-1 font-medium">Cycle</th>
              <th className="py-1 font-medium">Questions</th>
              <th className="py-1 font-medium">Mean</th>
              <th className="py-1 font-medium">MAE</th>
            </tr>
          </thead>
          <tbody>
            {payload.cycles.map((cycle) => (
              <tr key={cycle.cycle} className="border-t border-line">
                <td className="py-1.5">{cycle.cycle}</td>
                <td>{count(cycle.n_questions)}</td>
                <td>{points(cycle.mean_signed_error)}</td>
                <td>{magnitude(cycle.mae)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card className="lg:col-span-5">
        <h3 className="font-serif text-xl">By days before the election</h3>
        <div className="mt-4 grid gap-3 sm:grid-cols-5">
          {payload.timing.map((band) => (
            <div key={band.timing} className="rounded-md border border-line bg-paper px-3 py-3">
              <p className="text-xs uppercase tracking-wide text-muted">{band.timing}</p>
              <p className="mt-2 font-serif text-2xl">{points(band.mean_signed_error, 1)}</p>
              <p className="mt-1 text-xs text-muted">
                {count(band.n)} questions · MAE {magnitude(band.mae, 1)}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
