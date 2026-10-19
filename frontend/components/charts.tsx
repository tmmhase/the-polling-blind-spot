import type { Histogram } from "@/lib/types";

const AXIS = "#5e584e";
const GRID = "#e4dcd0";
const INK = "#1c1915";

export function HistogramChart({
  histogram,
  mean,
  height = 176,
}: {
  histogram: Histogram;
  mean?: number | null;
  height?: number;
}) {
  const width = 640;
  const padL = 32;
  const padR = 8;
  const padT = 12;
  const padB = 28;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const peak = Math.max(...histogram.counts, 1);
  const barW = innerW / histogram.counts.length;
  const xOf = (value: number) => padL + ((value - histogram.start) / histogram.step) * barW;
  const ticks = histogram.edges.filter((_, index) => index % 4 === 0);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img">
      {histogram.counts.map((count, index) => {
        const barH = (count / peak) * innerH;
        const edge = histogram.edges[index];
        const fill = edge + histogram.step / 2 >= 0 ? "#1d4e89" : "#8d2f2f";
        return (
          <rect
            key={edge}
            x={padL + index * barW + 0.6}
            y={padT + innerH - barH}
            width={Math.max(barW - 1.2, 0.5)}
            height={barH}
            fill={fill}
            opacity={0.85}
          >
            <title>{`${edge} to ${histogram.edges[index + 1]}: ${count}`}</title>
          </rect>
        );
      })}
      <line x1={padL} x2={width - padR} y1={padT + innerH} y2={padT + innerH} stroke={GRID} />
      {mean != null ? (
        <line x1={xOf(mean)} x2={xOf(mean)} y1={padT} y2={padT + innerH} stroke={INK} strokeDasharray="3 3" />
      ) : null}
      <line x1={xOf(0)} x2={xOf(0)} y1={padT} y2={padT + innerH} stroke={AXIS} strokeOpacity={0.45} />
      {ticks.map((tick) => (
        <text key={tick} x={xOf(tick)} y={height - 8} textAnchor="middle" fontSize="11" fill={AXIS}>
          {tick}
        </text>
      ))}
    </svg>
  );
}

export function DivergingBars({
  rows,
}: {
  rows: { label: string; value: number; note: string }[];
}) {
  const width = 680;
  const rowH = 28;
  const padL = 248;
  const padR = 12;
  const height = rows.length * rowH + 28;
  const max = Math.max(...rows.map((row) => Math.abs(row.value)), 1);
  const mid = padL + (width - padL - padR) / 2;
  const scale = (width - padL - padR) / 2 / max;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img">
      <line x1={mid} x2={mid} y1={4} y2={height - 22} stroke={GRID} />
      {rows.map((row, index) => {
        const y = 8 + index * rowH;
        const length = row.value * scale;
        const positive = row.value >= 0;
        return (
          <g key={row.label}>
            <text x={padL - 8} y={y + 14} textAnchor="end" fontSize="12" fill={INK}>
              {row.label}
              <tspan fill={AXIS}>{`  ${row.note}`}</tspan>
            </text>
            <rect
              x={positive ? mid : mid + length}
              y={y + 4}
              width={Math.abs(length)}
              height={14}
              fill={positive ? "#1d4e89" : "#8d2f2f"}
              opacity={0.88}
            >
              <title>{`${row.label}: ${row.value} (${row.note})`}</title>
            </rect>
          </g>
        );
      })}
      <text x={mid} y={height - 6} textAnchor="middle" fontSize="11" fill={AXIS}>
        0
      </text>
    </svg>
  );
}

export function StackedShares({
  groups,
}: {
  groups: { label: string; predictiveSd: number; parts: { key: string; label: string; share: number }[] }[];
}) {
  const colors: Record<string, string> = {
    sampling: "#c4b49a",
    house: "#8d4e2f",
    race: "#1d4e89",
    cycle: "#3f6f5b",
    mean_parameter: "#5e584e",
  };
  const width = 680;
  const rowH = 42;
  const padL = 210;
  const height = groups.length * rowH + 36;
  const barW = width - padL - 56;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img">
      {groups.map((group, index) => {
        let cursor = padL;
        const y = 10 + index * rowH;
        return (
          <g key={group.label}>
            <text x={padL - 10} y={y + 16} textAnchor="end" fontSize="12" fill={INK}>
              {group.label}
            </text>
            {group.parts.map((part) => {
              const widthPart = Math.max(part.share, 0) * barW;
              const node = (
                <rect key={part.key} x={cursor} y={y} width={widthPart} height={20} fill={colors[part.key] ?? "#999"}>
                  <title>{`${part.label}: ${(part.share * 100).toFixed(1)}%`}</title>
                </rect>
              );
              cursor += widthPart;
              return node;
            })}
            <text x={padL + barW + 8} y={y + 14} fontSize="11" fill={AXIS}>
              SD {group.predictiveSd.toFixed(1)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function CoverageChart({
  groups,
}: {
  groups: { label: string; coverage50: number; coverage80: number; coverage95: number }[];
}) {
  const width = 640;
  const height = 220;
  const padL = 36;
  const padB = 28;
  const padT = 12;
  const padR = 8;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const groupW = innerW / groups.length;
  const barW = groupW / 4.4;
  const yOf = (value: number) => padT + innerH - value * innerH;
  const guides = [0.5, 0.8, 0.95];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img">
      {guides.map((guide) => (
        <g key={guide}>
          <line x1={padL} x2={width - padR} y1={yOf(guide)} y2={yOf(guide)} stroke={GRID} strokeDasharray="3 3" />
          <text x={2} y={yOf(guide) + 3} fontSize="10" fill={AXIS}>
            {Math.round(guide * 100)}
          </text>
        </g>
      ))}
      {groups.map((group, index) => {
        const origin = padL + index * groupW + groupW * 0.18;
        const bars = [
          [group.coverage50, "#c4b8a5"],
          [group.coverage80, "#1d4e89"],
          [group.coverage95, "#8d4e2f"],
        ] as const;
        return (
          <g key={group.label}>
            {bars.map(([value, fill], barIndex) => (
              <rect
                key={fill}
                x={origin + barIndex * (barW + 2)}
                y={yOf(value)}
                width={barW}
                height={value * innerH}
                fill={fill}
              >
                <title>{`${group.label}: ${(value * 100).toFixed(1)}%`}</title>
              </rect>
            ))}
            <text x={origin + barW * 1.6} y={height - 8} textAnchor="middle" fontSize="12" fill={INK}>
              {group.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function MarginScatter({
  points,
  result,
  onHover,
}: {
  points: { id: string; x: number; y: number; title: string }[];
  result: number | null;
  onHover: (id: string | null) => void;
}) {
  const width = 720;
  const height = 280;
  const padL = 44;
  const padR = 16;
  const padT = 16;
  const padB = 32;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  if (points.length === 0) {
    return <p className="text-sm text-muted">This contest has no dated two-party margins to plot.</p>;
  }
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  if (result != null) ys.push(result);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const yPad = Math.max((maxY - minY) * 0.12, 1);
  const y0 = minY - yPad;
  const y1 = maxY + yPad;
  const xSpan = maxX - minX || 1;
  const xOf = (value: number) => padL + ((value - minX) / xSpan) * innerW;
  const yOf = (value: number) => padT + innerH - ((value - y0) / (y1 - y0)) * innerH;
  const yTicks = tickValues(y0, y1, 5);
  const xTicks = [minX, minX + xSpan / 2, maxX];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img">
      {yTicks.map((tick) => (
        <g key={tick}>
          <line x1={padL} x2={width - padR} y1={yOf(tick)} y2={yOf(tick)} stroke={GRID} />
          <text x={padL - 6} y={yOf(tick) + 4} textAnchor="end" fontSize="11" fill={AXIS}>
            {tick > 0 ? `+${tick.toFixed(0)}` : tick.toFixed(0)}
          </text>
        </g>
      ))}
      {result != null ? (
        <line
          x1={padL}
          x2={width - padR}
          y1={yOf(result)}
          y2={yOf(result)}
          stroke="#8d4e2f"
          strokeDasharray="5 4"
          strokeWidth={1.4}
        />
      ) : null}
      {points.map((point) => (
        <circle
          key={point.id}
          cx={xOf(point.x)}
          cy={yOf(point.y)}
          r={points.length > 180 ? 3 : 4}
          fill="#1c1915"
          opacity={0.72}
          onMouseEnter={() => onHover(point.id)}
          onMouseLeave={() => onHover(null)}
        >
          <title>{point.title}</title>
        </circle>
      ))}
      {xTicks.map((tick) => (
        <text key={tick} x={xOf(tick)} y={height - 8} textAnchor="middle" fontSize="11" fill={AXIS}>
          {formatAxisDate(tick)}
        </text>
      ))}
    </svg>
  );
}

function tickValues(min: number, max: number, target: number): number[] {
  const span = max - min || 1;
  const rough = span / target;
  const power = Math.pow(10, Math.floor(Math.log10(rough)));
  const error = rough / power;
  const step = (error >= 7.5 ? 10 : error >= 3.5 ? 5 : error >= 1.5 ? 2 : 1) * power;
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let value = start; value <= max + step * 0.01; value += step) {
    ticks.push(Number(value.toFixed(6)));
    if (ticks.length > 8) break;
  }
  return ticks;
}

function formatAxisDate(timestamp: number): string {
  const date = new Date(timestamp);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}
