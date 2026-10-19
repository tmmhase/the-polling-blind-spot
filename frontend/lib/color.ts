const STOPS: [number, string][] = [
  [-10, "#7a2424"],
  [-6, "#b85a4a"],
  [-2, "#e7cdc2"],
  [0, "#f4f0e6"],
  [2, "#c9d6e6"],
  [6, "#4d78a8"],
  [10, "#1a3e6e"],
];

export const COLOR_CAP = 10;

export function errorColor(value: number): string {
  const capped = Math.max(-COLOR_CAP, Math.min(COLOR_CAP, value));
  let lower = STOPS[0];
  let upper = STOPS[STOPS.length - 1];
  for (let index = 0; index < STOPS.length - 1; index += 1) {
    if (capped >= STOPS[index][0] && capped <= STOPS[index + 1][0]) {
      lower = STOPS[index];
      upper = STOPS[index + 1];
      break;
    }
  }
  const span = upper[0] - lower[0];
  const t = span === 0 ? 0 : (capped - lower[0]) / span;
  return mix(lower[1], upper[1], t);
}

export function legendGradient(): string {
  const stops = STOPS.map(([value, color]) => {
    const position = ((value + COLOR_CAP) / (COLOR_CAP * 2)) * 100;
    return `${color} ${position}%`;
  });
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

function mix(start: string, end: string, t: number): string {
  const channel = (hex: string, offset: number) => parseInt(hex.slice(offset, offset + 2), 16);
  const blend = (offset: number) =>
    Math.round(channel(start, offset) + (channel(end, offset) - channel(start, offset)) * t)
      .toString(16)
      .padStart(2, "0");
  return `#${blend(1)}${blend(3)}${blend(5)}`;
}
