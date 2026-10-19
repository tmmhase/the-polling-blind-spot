import { Card } from "@/components/ui";
import type { NotesPayload } from "@/lib/types";

export function NotesPanel({ payload }: { payload: NotesPayload }) {
  return (
    <div className="space-y-4">
      <Card>
        <h3 className="font-serif text-xl">What is being measured</h3>
        <p className="mt-3 text-sm leading-relaxed text-ink">{payload.error_definition}</p>
        <p className="mt-3 text-sm leading-relaxed text-muted">{payload.margin_definition}</p>
        <p className="mt-3 text-sm leading-relaxed text-ink">{payload.model}</p>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <RuleList title="Which questions are scored" items={payload.inclusion_rules} />
        <RuleList title="How results stay out of the pre-election average" items={payload.analysis_leakage_controls} />
        <RuleList title="How the backtest stays out of the scored cycle" items={payload.model_leakage_controls} />
        <RuleList title="Model limitations" items={payload.limitations} />
      </div>
      <Card>
        <h3 className="font-serif text-xl">Priors and sampler</h3>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          {Object.entries(payload.priors).map(([name, prior]) => (
            <div key={name} className="border-t border-line py-2">
              <dt className="text-muted">{name}</dt>
              <dd>{prior}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-sm text-muted">{payload.sampler.algorithm}</p>
      </Card>
      <div className="grid gap-4 lg:grid-cols-3">
        {payload.sources.map((source) => (
          <Card key={source.id}>
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-copper">{source.role}</p>
            <h3 className="mt-2 font-serif text-xl leading-tight">{source.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{source.coverage}</p>
            <p className="mt-3 text-sm">
              <a className="underline decoration-line underline-offset-2" href={source.license_url}>
                {source.license}
              </a>
            </p>
            <ul className="mt-3 space-y-2 text-sm leading-relaxed text-muted">
              {source.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <p className="mt-3 text-xs">
              <a className="underline decoration-line underline-offset-2" href={source.url}>
                Source
              </a>
              {" · "}
              <a className="underline decoration-line underline-offset-2" href={source.documentation_url}>
                Documentation
              </a>
              {source.snapshot_url ? (
                <>
                  {" · "}
                  <a className="underline decoration-line underline-offset-2" href={source.snapshot_url}>
                    Snapshot
                  </a>
                </>
              ) : null}
            </p>
          </Card>
        ))}
      </div>
    </div>
  );
}

function RuleList({ title, items }: { title: string; items: string[] }) {
  return (
    <Card>
      <h3 className="font-serif text-xl">{title}</h3>
      <ul className="mt-3 list-disc space-y-2 pl-4 text-sm leading-relaxed text-muted">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Card>
  );
}
