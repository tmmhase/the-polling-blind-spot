"use client";

import { useMemo, useState } from "react";
import atlas from "@/data/state-paths.json";
import { COLOR_CAP, errorColor, legendGradient } from "@/lib/color";
import { count, magnitude, points } from "@/lib/format";
import type { MapPayload, MapState } from "@/lib/types";
import { Card } from "@/components/ui";

const NO_DATA = "#e4dccb";

export function SenateMap({
  payload,
  selected,
  onSelect,
}: {
  payload: MapPayload;
  selected: string | null;
  onSelect: (statePo: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const [muteSparse, setMuteSparse] = useState(false);
  const byCode = useMemo(
    () => new Map(payload.states.map((state) => [state.state_po, state])),
    [payload.states],
  );
  const activeCode = hover ?? selected;
  const active = activeCode ? byCode.get(activeCode) ?? null : null;
  const ranked = payload.states
    .filter((state) => state.mean_signed_error != null)
    .slice()
    .sort((a, b) => (a.mean_signed_error ?? 0) - (b.mean_signed_error ?? 0));

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_20rem]">
      <Card className="p-3 sm:p-4">
        <svg viewBox={atlas.viewBox} className="h-auto w-full" role="group" aria-label="U.S. Senate states">
          <defs>
            <pattern id="sparse-hatch" width="6" height="6" patternUnits="userSpaceOnUse">
              <path d="M0 6 L6 0" stroke="#1c1915" strokeWidth="0.7" opacity="0.45" />
            </pattern>
          </defs>
          {atlas.states.map((shape) => {
            const state = byCode.get(shape.state_po);
            const value = state?.mean_signed_error;
            const sparse = Boolean(state && state.has_scored_questions && state.n_questions < 10 && muteSparse);
            const fill = value == null ? NO_DATA : errorColor(value);
            const isActive = shape.state_po === activeCode;
            return (
              <g key={shape.state_po}>
                <path
                  d={shape.d}
                  className="state-shape"
                  fill={fill}
                  stroke={isActive ? "#1c1915" : "#faf7f1"}
                  strokeWidth={isActive ? 1.8 : 0.6}
                  role="button"
                  tabIndex={0}
                  aria-label={ariaLabel(shape.name, state)}
                  onMouseEnter={() => setHover(shape.state_po)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(shape.state_po)}
                  onBlur={() => setHover(null)}
                  onClick={() => onSelect(shape.state_po)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(shape.state_po);
                    }
                  }}
                />
                {sparse ? <path d={shape.d} fill="url(#sparse-hatch)" pointerEvents="none" /> : null}
              </g>
            );
          })}
        </svg>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-md flex-1">
            <div className="h-3 rounded-full border border-line" style={{ background: legendGradient() }} />
            <div className="mt-1 flex justify-between gap-2 text-[0.7rem] uppercase tracking-wide text-muted">
              <span>More Republican</span>
              <span>0</span>
              <span>More Democratic</span>
            </div>
            <p className="mt-1 text-xs text-muted">Color runs from −10 to +10 points and holds the end color past that.</p>
          </div>
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={muteSparse}
              onChange={(event) => setMuteSparse(event.target.checked)}
              className="accent-copper"
            />
            Hatch states with fewer than 10 questions
          </label>
        </div>
      </Card>
      <div className="space-y-3">
        <Card>
          {active ? <StateCard state={active} /> : <p className="text-sm text-muted">Hover or focus a state.</p>}
        </Card>
        <Card>
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-copper">Ends of the state means</p>
          <ExtremeList title="More Republican than the result" rows={ranked.slice(0, 4)} />
          <ExtremeList title="More Democratic than the result" rows={ranked.slice(-4).reverse()} />
        </Card>
      </div>
    </div>
  );
}

function StateCard({ state }: { state: MapState }) {
  return (
    <div>
      <p className="font-serif text-2xl leading-none">{state.state_name}</p>
      {state.has_scored_questions ? (
        <>
          <p className="mt-3 font-serif text-4xl leading-none">{points(state.mean_signed_error, 1)}</p>
          <p className="mt-1 text-sm text-muted">mean signed error, points</p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-muted">Questions</dt>
              <dd>{count(state.n_questions)}</dd>
            </div>
            <div>
              <dt className="text-muted">Contests</dt>
              <dd>{count(state.n_races)}</dd>
            </div>
            <div>
              <dt className="text-muted">Median error</dt>
              <dd>{points(state.median_signed_error)}</dd>
            </div>
            <div>
              <dt className="text-muted">MAE</dt>
              <dd>{magnitude(state.mae)}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="mt-3 text-sm leading-relaxed text-muted">No scored questions in the 2018–2024 error file.</p>
      )}
      {state.exclusions.length > 0 ? (
        <ul className="mt-4 space-y-1 text-sm text-muted">
          {state.exclusions.map((item) => (
            <li key={item.reason}>
              {item.label}: {count(item.n_questions)} excluded
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ExtremeList({ title, rows }: { title: string; rows: MapState[] }) {
  return (
    <div className="mt-3">
      <p className="text-sm text-ink">{title}</p>
      <ul className="mt-1 space-y-1 text-sm text-muted">
        {rows.map((row) => (
          <li key={row.state_po} className="flex justify-between gap-3">
            <span>
              {row.state_name}
              <span className="text-xs"> · {count(row.n_questions)}</span>
            </span>
            <span className="text-ink">{points(row.mean_signed_error, 1)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ariaLabel(name: string, state: MapState | undefined): string {
  if (!state || !state.has_scored_questions || state.mean_signed_error == null) {
    return `${name}, no scored questions`;
  }
  return `${name}, mean signed error ${points(state.mean_signed_error, 1)} points, ${state.n_questions} questions`;
}
