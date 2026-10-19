"use client";

import { useEffect, useMemo, useState } from "react";
import { MarginScatter } from "@/components/charts";
import { Card, Notice } from "@/components/ui";
import { getJson } from "@/lib/api";
import { count, points, shortDate } from "@/lib/format";
import type { MapState, StateDetail, StateQuestion } from "@/lib/types";

export function TrendPanel({
  states,
  selected,
  onSelect,
}: {
  states: MapState[];
  selected: string | null;
  onSelect: (statePo: string) => void;
}) {
  const [detail, setDetail] = useState<StateDetail | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [contestId, setContestId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      setStatus("idle");
      return;
    }
    let cancel = false;
    setStatus("loading");
    getJson<StateDetail>(`/api/states/${selected}`)
      .then((body) => {
        if (cancel) return;
        setDetail(body);
        const preferred = body.races.slice().sort((a, b) => b.n_questions - a.n_questions || b.election_year - a.election_year)[0];
        setContestId(preferred?.contest_id ?? null);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancel) setStatus("error");
      });
    return () => {
      cancel = true;
    };
  }, [selected]);

  const questions = useMemo(
    () => (detail?.questions ?? []).filter((row) => row.contest_id === contestId),
    [detail, contestId],
  );
  const race = detail?.races.find((row) => row.contest_id === contestId) ?? null;
  const hovered = questions.find((row) => row.question_id === hoverId) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="text-sm text-muted">
          State
          <select
            value={selected ?? ""}
            onChange={(event) => onSelect(event.target.value)}
            className="mt-1 block rounded border border-line bg-card px-3 py-2 text-ink"
          >
            <option value="" disabled>
              Choose a state
            </option>
            {states
              .filter((state) => state.has_scored_questions)
              .slice()
              .sort((a, b) => a.state_name.localeCompare(b.state_name))
              .map((state) => (
                <option key={state.state_po} value={state.state_po}>
                  {state.state_name}
                </option>
              ))}
          </select>
        </label>
        {detail && detail.races.length > 0 ? (
          <label className="text-sm text-muted">
            Contest
            <select
              value={contestId ?? ""}
              onChange={(event) => setContestId(event.target.value)}
              className="mt-1 block max-w-xl rounded border border-line bg-card px-3 py-2 text-ink"
            >
              {detail.races.map((row) => (
                <option key={row.contest_id} value={row.contest_id}>
                  {row.election_year} {row.stage}
                  {row.special ? " special" : ""} · {row.dem_candidate} vs {row.rep_candidate} ·{" "}
                  {row.n_questions} questions
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
      {status === "idle" ? <Notice>Select a state on the map or in the menu to read its scored questions.</Notice> : null}
      {status === "loading" ? <p className="text-sm text-muted">Loading scored questions…</p> : null}
      {status === "error" ? <Notice>The state series did not load. The API may be unavailable.</Notice> : null}
      {status === "ready" && detail && !detail.has_scored_questions ? (
        <Notice>
          {detail.state_name} has no scored questions in the historical error file.
          {detail.exclusions.length > 0
            ? ` Excluded rows: ${detail.exclusions.map((item) => `${item.label} (${item.n_questions})`).join("; ")}.`
            : " The exclusion table also has no rows for this state."}
        </Notice>
      ) : null}
      {status === "ready" && race ? (
        <>
          <Notice>{detail?.result_role}</Notice>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_16rem]">
            <Card>
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-serif text-xl">
                  {race.dem_candidate} − {race.rep_candidate}
                </h3>
                <p className="text-sm text-muted">
                  Unweighted poll mean {points(race.poll_margin_two_party_mean)} · result{" "}
                  {points(race.result_margin_two_party)} · error {points(race.error_of_unweighted_mean)}
                </p>
              </div>
              <MarginScatter
                result={race.result_margin_two_party}
                onHover={setHoverId}
                points={questions.flatMap((row) => {
                  if (row.poll_margin_two_party == null) return [];
                  const stamp = Date.parse(`${row.end_date}T00:00:00Z`);
                  if (Number.isNaN(stamp)) return [];
                  return [
                    {
                      id: row.question_id,
                      x: stamp,
                      y: row.poll_margin_two_party,
                      title: `${row.pollster}, ${row.end_date}, margin ${row.poll_margin_two_party}`,
                    },
                  ];
                })}
              />
              <p className="mt-2 text-xs leading-relaxed text-muted">
                Dots are scored questions. The vertical position is the two-party poll margin, Democratic
                share minus Republican share, rescaled to the two-candidate denominator. The copper line is
                the official two-candidate margin{race.result_unofficial ? ", flagged unofficial in the results file" : ""}.
              </p>
              <QuestionReadout question={hovered} />
            </Card>
            <Card>
              <h3 className="font-serif text-xl">Contests</h3>
              <ul className="mt-3 space-y-3">
                {detail?.races.map((row) => (
                  <li key={row.contest_id}>
                    <button
                      type="button"
                      onClick={() => setContestId(row.contest_id)}
                      className={`w-full rounded border px-3 py-2 text-left text-sm ${
                        row.contest_id === contestId ? "border-ink bg-paper" : "border-line"
                      }`}
                    >
                      <span className="block text-ink">
                        {row.election_year} {row.stage}
                      </span>
                      <span className="mt-1 block text-muted">
                        {count(row.n_questions)} questions · error {points(row.error_of_unweighted_mean, 1)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
          <Card>
            <div className="max-h-80 overflow-auto">
              <table className="w-full min-w-[46rem] text-sm">
                <thead className="sticky top-0 bg-card text-left text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="py-2 font-medium">End date</th>
                    <th className="py-2 font-medium">Pollster</th>
                    <th className="py-2 font-medium">Margin</th>
                    <th className="py-2 font-medium">Error</th>
                    <th className="py-2 font-medium">Sample</th>
                    <th className="py-2 font-medium">Methodology</th>
                  </tr>
                </thead>
                <tbody>
                  {questions.map((row) => (
                    <tr
                      key={row.question_id}
                      className={`border-t border-line ${row.question_id === hoverId ? "bg-paper" : ""}`}
                      onMouseEnter={() => setHoverId(row.question_id)}
                    >
                      <td className="py-1.5">{shortDate(row.end_date)}</td>
                      <td>{row.pollster}</td>
                      <td>{points(row.poll_margin_two_party)}</td>
                      <td>{points(row.error_two_party)}</td>
                      <td>{row.sample_size == null ? "—" : count(row.sample_size)}</td>
                      <td className="text-muted">{row.methodology ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function QuestionReadout({ question }: { question: StateQuestion | null }) {
  if (!question) return <p className="mt-3 text-sm text-muted">Hover a point or a table row.</p>;
  return (
    <p className="mt-3 text-sm text-ink">
      {question.pollster} · {shortDate(question.end_date)} · margin {points(question.poll_margin_two_party)} ·
      error {points(question.error_two_party)}
      {question.sample_size != null ? ` · n ${count(question.sample_size)}` : ""}
      {question.population ? ` · ${question.population}` : ""}
    </p>
  );
}
