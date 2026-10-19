/**
 * Project a US-Atlas states TopoJSON into SVG paths for the Senate map.
 *
 * Input default: /tmp/us-atlas/states-10m.json
 * Source: https://cdn.jsdelivr.net/npm/us-atlas@3.0.1/states-10m.json
 *
 * The committed file is frontend/data/state-paths.json. Re-run with:
 *   npm run map -- /tmp/us-atlas/states-10m.json
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { geoAlbersUsa, geoPath } from "d3-geo";
import { feature } from "topojson-client";

const FIPS = {
  "01": "AL",
  "02": "AK",
  "04": "AZ",
  "05": "AR",
  "06": "CA",
  "08": "CO",
  "09": "CT",
  10: "DE",
  12: "FL",
  13: "GA",
  15: "HI",
  16: "ID",
  17: "IL",
  18: "IN",
  19: "IA",
  20: "KS",
  21: "KY",
  22: "LA",
  23: "ME",
  24: "MD",
  25: "MA",
  26: "MI",
  27: "MN",
  28: "MS",
  29: "MO",
  30: "MT",
  31: "NE",
  32: "NV",
  33: "NH",
  34: "NJ",
  35: "NM",
  36: "NY",
  37: "NC",
  38: "ND",
  39: "OH",
  40: "OK",
  41: "OR",
  42: "PA",
  44: "RI",
  45: "SC",
  46: "SD",
  47: "TN",
  48: "TX",
  49: "UT",
  50: "VT",
  51: "VA",
  53: "WA",
  54: "WV",
  55: "WI",
  56: "WY",
};

const here = dirname(fileURLToPath(import.meta.url));
const input = process.argv[2] ?? "/tmp/us-atlas/states-10m.json";
const topo = JSON.parse(readFileSync(input, "utf8"));
const collection = feature(topo, topo.objects.states);
const width = 960;
const height = 600;
const projection = geoAlbersUsa().fitExtent(
  [
    [8, 8],
    [width - 8, height - 8],
  ],
  collection,
);
const path = geoPath(projection);
const states = collection.features
  .map((shape) => {
    const fips = String(shape.id).padStart(2, "0");
    const statePo = FIPS[fips] ?? FIPS[Number(fips)];
    if (!statePo) return null;
    const centroid = path.centroid(shape);
    return {
      state_po: statePo,
      name: shape.properties.name,
      d: path(shape),
      cx: Number(centroid[0].toFixed(1)),
      cy: Number(centroid[1].toFixed(1)),
    };
  })
  .filter(Boolean)
  .sort((a, b) => a.state_po.localeCompare(b.state_po));

const output = resolve(here, "../data/state-paths.json");
mkdirSync(dirname(output), { recursive: true });
writeFileSync(
  output,
  JSON.stringify({ viewBox: `0 0 ${width} ${height}`, states }) + "\n",
);
console.log(`wrote ${states.length} states to ${output}`);
