/** Live world map (issues #40/#47): active countries pulse over the same
 *  bundled basemap as the choropleth — no tiles, no CDN. Quiet countries
 *  fade out with the payload; the outline keeps the world readable when
 *  only one country is active. */

import { useTranslation } from "react-i18next";
import { MAP_HEIGHT, MAP_WIDTH, projectPoint, WORLD_SHAPES } from "./Choropleth";

// ISO 3166-1 alpha-2 → [longitude, latitude] centroids (common subset;
// unknown codes simply don't render — the ranked list below the map
// stays complete).
const CENTROIDS: Record<string, [number, number]> = {
  FR: [2.2, 46.2], US: [-98.5, 39.8], DE: [10.4, 51.1], GB: [-3.4, 55.4],
  ES: [-3.7, 40.4], IT: [12.6, 41.9], PT: [-8.2, 39.4], BE: [4.5, 50.5],
  NL: [5.3, 52.1], CH: [8.2, 46.8], AT: [14.6, 47.5], IE: [-8.2, 53.4],
  PL: [19.1, 51.9], SE: [18.6, 60.1], NO: [8.5, 60.5], FI: [25.7, 61.9],
  DK: [9.5, 56.3], CA: [-106.3, 56.1], MX: [-102.6, 23.6], BR: [-51.9, -14.2],
  AR: [-63.6, -38.4], CL: [-71.5, -35.7], CO: [-74.3, 4.6], PE: [-75.0, -9.2],
  MA: [-7.1, 31.8], DZ: [1.7, 28.0], TN: [9.5, 33.9], SN: [-14.5, 14.5],
  CI: [-5.5, 7.5], EG: [30.8, 26.8], ZA: [22.9, -30.6], NG: [8.7, 9.1],
  KE: [37.9, -0.02], IN: [78.9, 20.6], CN: [104.2, 35.9], JP: [138.3, 36.2],
  KR: [127.8, 35.9], SG: [103.8, 1.35], HK: [114.1, 22.4], TW: [121.0, 23.7],
  TH: [100.9, 15.9], VN: [108.3, 14.1], ID: [113.9, -0.8], MY: [101.9, 4.2],
  PH: [121.8, 12.9], AU: [133.8, -25.3], NZ: [174.9, -40.9], RU: [105.3, 61.5],
  UA: [31.2, 48.4], TR: [35.2, 39.0], IL: [34.9, 31.0], SA: [45.1, 23.9],
  AE: [53.8, 23.4], QA: [51.2, 25.4], GR: [21.8, 39.1], RO: [25.0, 45.9],
  CZ: [15.5, 49.8], HU: [19.5, 47.2], BG: [25.5, 42.7], HR: [15.2, 45.1],
  RS: [21.0, 44.0], SK: [19.7, 48.7], SI: [14.9, 46.1], LT: [23.9, 55.2],
  LV: [24.6, 56.9], EE: [25.0, 58.6], IS: [-19.0, 64.9], LU: [6.1, 49.8],
};

export default function WorldLive({
  countries,
}: {
  countries: { country: string; value: number }[];
}) {
  const { t } = useTranslation();
  const max = Math.max(1, ...countries.map((c) => c.value));
  return (
    <div>
      <svg
        viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
        className="mx-auto block w-full max-w-3xl rounded-lg border border-line bg-paper"
      >
        {WORLD_SHAPES.map((shape) => (
          <path
            key={shape.a2 ?? shape.name}
            d={shape.d}
            fill="var(--surface)"
            stroke="var(--line)"
            strokeWidth={0.5}
          />
        ))}
        {countries.map(({ country, value }) => {
          const centroid = CENTROIDS[country];
          if (!centroid) return null;
          const [x, y] = projectPoint(centroid[0], centroid[1]);
          const radius = 5 + 12 * (value / max);
          return (
            <g key={country}>
              <circle cx={x} cy={y} r={radius} fill="var(--color-flame)" opacity="0.25">
                <animate
                  attributeName="r"
                  values={`${radius};${radius * 1.8};${radius}`}
                  dur="2.4s"
                  repeatCount="indefinite"
                />
              </circle>
              <circle cx={x} cy={y} r={Math.max(3, radius * 0.45)} fill="var(--color-flame)" />
              <title>{`${country}: ${value}`}</title>
            </g>
          );
        })}
      </svg>
      {countries.length === 0 && (
        <p className="mt-1 text-center text-xs text-ink-soft">{t("web.empty")}</p>
      )}
    </div>
  );
}
