"use client";

import { useMemo, useState } from "react";
import { DivergingBars } from "@/components/charts";
import { Card } from "@/components/ui";
import { count, magnitude, points } from "@/lib/format";
import type { PollsterRow, PollstersPayload } from "@/lib/types";

const FLOORS = [10, 20, 40];
type SortKey = "n_questions" | "mean_signed_error" | "mae";

export function PollsterPanel({ payload }: { payload: PollstersPayload }) {
  const [floor, setFloor] = useState(20);
  const [sortKey, setSortKey] = useState<SortKey>("n_questions");
  const [descending, setDescending] = useState(true);
  const rows = useMemo(() => {
    const filtered = payload.pollsters.filter((row) => row.n_questions >= floor);
    const direction = descending ? -1 : 1;
    return filtered.slice().sort((a, b) => {
      const left = a[sortKey] ?? 0;
      const right = b[sortKey] ?? 0;
      if (left === right) return a.pollster.localeCompare(b.pollster);
      return left > right ? direction : -direction;
    });
  }, [payload.pollsters, floor, sortKey, descending]);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h3 className="font-serif text-xl">Published methodology</h3>
          <p className="mt-1 text-sm leading-relaxed text-muted">{payload.methodology_rule}</p>
          <div className="mt-3">
            <DivergingBars
              rows={payload.methodology.map((row) => ({
                label: row.methodology,
                value: row.mean_signed_error ?? 0,
                note: count(row.n_questions),
              }))}
            />
          </div>
        </Card>
        <Card>
          <h3 className="font-serif text-xl">Sample population</h3>
          <p className="mt-1 text-sm leading-relaxed text-muted">{payload.population_note}</p>
          <div className="mt-3">
            <DivergingBars
              rows={payload.population.map((row) => ({
                label: row.label,
                value: row.mean_signed_error ?? 0,
                note: count(row.n),
              }))}
            />
          </div>
          <table className="mt-2 w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-1 font-medium">Population</th>
                <th className="py-1 font-medium">Mean</th>
                <th className="py-1 font-medium">MAE</th>
              </tr>
            </thead>
            <tbody>
              {payload.population.map((row) => (
                <tr key={row.population} className="border-t border-line">
                  <td className="py-1.5">
                    {row.label} <span className="text-muted">({row.population})</span>
                  </td>
                  <td>{points(row.mean_signed_error)}</td>
                  <td>{magnitude(row.mae)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="font-serif text-xl">Pollsters</h3>
            <p className="mt-1 text-sm text-muted">
              {count(rows.length)} firms with at least {floor} scored questions. Modal methodology is the
              most common published string for that firm.
            </p>
          </div>
          <div className="flex gap-1" role="group" aria-label="Minimum questions">
            {FLOORS.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setFloor(value)}
                className={`rounded border px-3 py-1 text-sm ${
                  floor === value ? "border-ink bg-ink text-paper" : "border-line bg-paper text-ink"
                }`}
              >
                {value}+
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4 max-h-[28rem] overflow-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="sticky top-0 bg-card text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-2 font-medium">Pollster</th>
                <SortHeader label="Questions" active={sortKey === "n_questions"} descending={descending} onClick={() => toggle("n_questions", sortKey, setSortKey, descending, setDescending)} />
                <th className="py-2 font-medium">Races</th>
                <SortHeader label="Mean error" active={sortKey === "mean_signed_error"} descending={descending} onClick={() => toggle("mean_signed_error", sortKey, setSortKey, descending, setDescending)} />
                <SortHeader label="MAE" active={sortKey === "mae"} descending={descending} onClick={() => toggle("mae", sortKey, setSortKey, descending, setDescending)} />
                <th className="py-2 font-medium">Modal methodology</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.pollster_key} className="border-t border-line">
                  <td className="py-1.5 pr-3">{row.pollster}</td>
                  <td>{count(row.n_questions)}</td>
                  <td>{count(row.n_races)}</td>
                  <td>{points(row.mean_signed_error)}</td>
                  <td>{magnitude(row.mae)}</td>
                  <td className="pr-2 text-muted">{row.modal_methodology ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function toggle(
  key: SortKey,
  sortKey: SortKey,
  setSortKey: (key: SortKey) => void,
  descending: boolean,
  setDescending: (value: boolean) => void,
) {
  if (sortKey === key) setDescending(!descending);
  else {
    setSortKey(key);
    setDescending(true);
  }
}

function SortHeader({
  label,
  active,
  descending,
  onClick,
}: {
  label: string;
  active: boolean;
  descending: boolean;
  onClick: () => void;
}) {
  return (
    <th className="py-2 font-medium">
      <button type="button" onClick={onClick} className="inline-flex items-center gap-1 uppercase">
        {label}
        <span aria-hidden="true">{active ? (descending ? "↓" : "↑") : ""}</span>
      </button>
    </th>
  );
}

export type { PollsterRow };
