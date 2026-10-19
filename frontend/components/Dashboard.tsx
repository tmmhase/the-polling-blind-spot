"use client";

import { useEffect, useState } from "react";
import { ErrorPanel } from "@/components/ErrorPanel";
import { NotesPanel } from "@/components/NotesPanel";
import { PollsterPanel } from "@/components/PollsterPanel";
import { SenateMap } from "@/components/SenateMap";
import { TrendPanel } from "@/components/TrendPanel";
import { UncertaintyPanel } from "@/components/UncertaintyPanel";
import { Section, TopBar } from "@/components/ui";
import { getJson } from "@/lib/api";
import { count, magnitude, points } from "@/lib/format";
import type { DashboardData } from "@/lib/types";

export function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;
    Promise.all([
      getJson<DashboardData["overview"]>("/api/overview"),
      getJson<DashboardData["map"]>("/api/map"),
      getJson<DashboardData["errors"]>("/api/errors"),
      getJson<DashboardData["pollsters"]>("/api/pollsters"),
      getJson<DashboardData["uncertainty"]>("/api/uncertainty"),
      getJson<DashboardData["notes"]>("/api/notes"),
    ])
      .then(([overview, map, errors, pollsters, uncertainty, notes]) => {
        if (!cancel) setData({ overview, map, errors, pollsters, uncertainty, notes });
      })
      .catch((reason: unknown) => {
        if (!cancel) setError(reason instanceof Error ? reason.message : "The API request failed.");
      });
    return () => {
      cancel = true;
    };
  }, []);

  return (
    <div id="top" className="min-h-screen">
      <TopBar />
      <main className="mx-auto max-w-6xl px-4 pb-20">
        <header className="py-10 sm:py-14">
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-copper">
            U.S. Senate · cycles 2018–2024
          </p>
          <h1 className="mt-3 max-w-3xl font-serif text-5xl leading-[1.05] text-ink sm:text-6xl">
            The Polling Blind Spot
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">
            Signed two-party error in historical Senate polls, and the part of that miss a contest
            still shares after sampling noise has been averaged down.
          </p>
          {data ? (
            <dl className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat
                label="Scored questions"
                value={count(data.overview.scored_questions)}
                detail="One row in the error file is one question."
              />
              <Stat
                label="Mean signed error"
                value={points(data.overview.poll_level.mean_signed_error, 2)}
                detail="Question-level. Positive is more Democratic than the result."
              />
              <Stat
                label="Mean absolute error"
                value={magnitude(data.overview.poll_level.mae, 2)}
                detail={`Race-level MAE ${magnitude(data.overview.race_level_unweighted_mean.mae)} across ${count(data.overview.races)} contests.`}
              />
              <Stat
                label="Race SD"
                value={magnitude(data.overview.model.sd_race_p50, 2)}
                detail="Posterior median of the contest-level standard deviation, in points."
              />
            </dl>
          ) : null}
        </header>
        {error ? (
          <p className="border-l-2 border-rep bg-card px-4 py-3 text-sm text-ink">
            The dashboard could not read the API ({error}). Start it with{" "}
            <code className="font-mono text-[0.85em]">python3 scripts/serve_api.py</code> and reload.
          </p>
        ) : null}
        {!data && !error ? <p className="text-sm text-muted">Loading the committed outputs…</p> : null}
        {data ? (
          <>
            <Section
              id="map"
              eyebrow="Map"
              title="Where Senate polls missed"
              lede={`${data.map.score_note} ${data.map.map_note} Color saturates at ±10 points; the card shows the unclipped mean.`}
            >
              <SenateMap payload={data.map} selected={selected} onSelect={setSelected} />
            </Section>
            <Section
              id="errors"
              eyebrow="Distribution"
              title="Historical polling error"
              lede={data.errors.definition}
            >
              <ErrorPanel payload={data.errors} />
            </Section>
            <Section
              id="pollsters"
              eyebrow="Methodology"
              title="Pollster and mode comparisons"
              lede="Bars are mean signed error. The count beside each label is the number of scored questions. A longer bar is a larger average miss, not a larger sample."
            >
              <PollsterPanel payload={data.pollsters} />
            </Section>
            <Section
              id="trends"
              eyebrow="State series"
              title="Polling margin against the result"
              lede="The contest menu opens on the race in that state with the most scored questions. Each dot is one scored question."
            >
              <TrendPanel states={data.map.states} selected={selected} onSelect={setSelected} />
            </Section>
            <Section
              id="uncertainty"
              eyebrow="Simulation"
              title="Uncertainty around a new contest"
              lede={data.uncertainty.equation}
            >
              <UncertaintyPanel payload={data.uncertainty} />
            </Section>
            <Section
              id="notes"
              eyebrow="Documentation"
              title="Assumptions and sources"
              lede="The model is fit to 2018–2024 signed errors. A later cycle such as 2026 can be scored from timing, sample size, and pollster id. This page does not attach a 2026 roster."
            >
              <NotesPanel payload={data.notes} />
            </Section>
            <footer className="border-t border-line pt-6 text-sm leading-relaxed text-muted">
              Outputs from the committed historical-error and uncertainty tables. Model seed{" "}
              {data.overview.model.seed}, {count(data.overview.model.draws)} retained draws.{" "}
              {count(data.overview.distinct_poll_ids)} distinct poll ids among{" "}
              {count(data.overview.scored_questions)} scored questions.{" "}
              {count(data.overview.model.n_polls_modeled)} polls enter the hierarchical model after
              questions that share a poll id are collapsed.
            </footer>
          </>
        ) : null}
      </main>
    </div>
  );
}

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-lg border border-line bg-card px-3 py-3 shadow-card">
      <dt className="text-[0.72rem] uppercase tracking-[0.12em] text-muted">{label}</dt>
      <dd className="mt-2 font-serif text-3xl leading-none">{value}</dd>
      <p className="mt-2 text-xs leading-relaxed text-muted">{detail}</p>
    </div>
  );
}
