/** Country choropleth (issue #50) — the basemap ships in the bundle
 *  (world-atlas TopoJSON + d3-geo), no tile server, no CDN: consistent with
 *  the self-hosted / EU-residency posture. Values are keyed by ISO 3166-1
 *  alpha-2, matching the registry's `country` dimension. */

import { useMemo } from "react";
import { geoNaturalEarth1, geoPath } from "d3-geo";
import { feature } from "topojson-client";
import type { FeatureCollection, Geometry } from "geojson";
import type { Topology, Objects } from "topojson-specification";
import { iso31661 } from "iso-3166";
import world from "world-atlas/countries-110m.json";

export const MAP_WIDTH = 960;
export const MAP_HEIGHT = 470;
const WIDTH = MAP_WIDTH;
const HEIGHT = MAP_HEIGHT;

interface CountryShape {
  a2: string | null;
  name: string;
  d: string;
}

const PROJECTION = (() => {
  const topology = world as unknown as Topology<Objects>;
  const collection = feature(
    topology,
    topology.objects.countries,
  ) as unknown as FeatureCollection<Geometry, { name?: string }>;
  return geoNaturalEarth1().fitExtent(
    [
      [4, 4],
      [WIDTH - 4, HEIGHT - 4],
    ],
    collection,
  );
})();

/** Project a [longitude, latitude] into the shared map space. */
export function projectPoint(lon: number, lat: number): [number, number] {
  return PROJECTION([lon, lat]) ?? [0, 0];
}

/** The bundled world outline, shared by the choropleth and the live map. */
export const WORLD_SHAPES: CountryShape[] = (() => {
  const numericToA2 = new Map(iso31661.map((c) => [c.numeric.padStart(3, "0"), c.alpha2]));
  const topology = world as unknown as Topology<Objects>;
  const collection = feature(
    topology,
    topology.objects.countries,
  ) as unknown as FeatureCollection<Geometry, { name?: string }>;
  const path = geoPath(PROJECTION);
  return collection.features
    .map((f) => ({
      a2: numericToA2.get(String(f.id).padStart(3, "0")) ?? null,
      name: f.properties?.name ?? "",
      d: path(f) ?? "",
    }))
    .filter((shape) => shape.d !== "" && shape.a2 !== "AQ");
})();

const SHAPES = WORLD_SHAPES;

/** ISO2 → value map from registry rows carrying a `country` key — the shape
 *  every map consumer (web, API, public) builds. */
export function countryValues(
  rows: { country?: unknown; value: number | null }[] | undefined,
): Map<string, number> {
  return new Map(
    (rows ?? [])
      .filter((row) => typeof row.country === "string" && row.country !== "")
      .map((row) => [String(row.country), row.value ?? 0]),
  );
}

export interface ChoroplethProps {
  /** ISO2 → value; countries absent from the map render as "no data" */
  values: Map<string, number>;
  selected?: string | null;
  onSelect?: (a2: string) => void;
  formatValue?: (value: number) => string;
  /** what the color encodes, announced in each country's label */
  legendLabel: string;
}

export default function Choropleth({
  values,
  selected,
  onSelect,
  formatValue = (v) => String(v),
  legendLabel,
}: ChoroplethProps) {
  const max = useMemo(() => Math.max(1, ...values.values()), [values]);

  const fillFor = (a2: string | null): string => {
    const value = a2 !== null ? values.get(a2) : undefined;
    if (value === undefined || value === 0) return "var(--surface)";
    const share = Math.round(15 + 80 * (value / max));
    return `color-mix(in srgb, var(--flame) ${share}%, var(--surface))`;
  };

  return (
    <figure>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full rounded-lg border border-line bg-paper"
        role="group"
        aria-label={legendLabel}
      >
        {SHAPES.map((shape) => {
          const value = shape.a2 !== null ? values.get(shape.a2) : undefined;
          const interactive = onSelect !== undefined && shape.a2 !== null;
          const label =
            value !== undefined
              ? `${shape.name} — ${formatValue(value)}`
              : shape.name;
          return (
            <path
              key={`${shape.a2 ?? shape.name}`}
              d={shape.d}
              fill={fillFor(shape.a2)}
              stroke={selected !== null && selected === shape.a2 ? "var(--flame)" : "var(--line)"}
              strokeWidth={selected !== null && selected === shape.a2 ? 1.6 : 0.5}
              className={interactive ? "cursor-pointer hover:brightness-95" : undefined}
              role={interactive ? "button" : undefined}
              tabIndex={interactive ? 0 : undefined}
              aria-label={label}
              onClick={interactive ? () => onSelect(shape.a2 as string) : undefined}
              onKeyDown={
                interactive
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelect(shape.a2 as string);
                      }
                    }
                  : undefined
              }
            >
              <title>{label}</title>
            </path>
          );
        })}
      </svg>
      <figcaption className="mt-1 flex items-center gap-2 text-[11px] text-ink-soft">
        <span>0</span>
        <span
          aria-hidden
          className="h-2 w-28 rounded-full border border-line"
          style={{
            background:
              "linear-gradient(to right, var(--surface), color-mix(in srgb, var(--flame) 95%, var(--surface)))",
          }}
        />
        <span className="tnum">{formatValue(max)}</span>
        <span className="ml-1">{legendLabel}</span>
      </figcaption>
    </figure>
  );
}
