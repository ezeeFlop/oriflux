/** Public dashboard (issues #41/#56): no auth, a curated read-only subset
 *  for a single project served through a signed share token. Every number
 *  goes through /public/{token}/query — the server rejects anything outside
 *  the allow-list, so this page can only ever show the safe subset. It is
 *  the product's shop window: new design system, light by default, and the
 *  same widgets as the private web view (Panel, RankedTable, Choropleth). */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import Choropleth from "../components/Choropleth";
import { Panel, RankedTable } from "../components/widgets";
import { formatNumber } from "../lib/format";

interface PublicRow {
  value: number | null;
  [dimension: string]: unknown;
}

async function publicQuery(token: string, body: object): Promise<PublicRow[]> {
  const response = await fetch(`/public/${token}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(String(response.status));
  return ((await response.json()).results ?? []) as PublicRow[];
}

const PERIOD = () => {
  const end = new Date();
  const start = new Date(end.getTime() - 30 * 24 * 3600 * 1000);
  return { start: start.toISOString(), end: end.toISOString() };
};

function Flame() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 text-flame" fill="currentColor" aria-hidden>
      <path d="M4 3h13l-2.5 3.5L17 10H6v11a2 2 0 0 1-2-2V3z" />
    </svg>
  );
}

export default function PublicView() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const period = PERIOD();

  const visitors = useQuery({
    queryKey: ["pub-visitors", token],
    queryFn: () => publicQuery(token, { metric: "visitors", period }),
    retry: false,
  });
  const pages = useQuery({
    queryKey: ["pub-pages", token],
    queryFn: () => publicQuery(token, { metric: "pageviews", dimensions: ["page"], period }),
  });
  const countries = useQuery({
    queryKey: ["pub-countries", token],
    queryFn: () =>
      publicQuery(token, { metric: "visitors", dimensions: ["country"], period }),
  });

  if (visitors.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper px-4">
        <div className="rounded-lg border border-dashed border-line bg-surface p-8 text-center">
          <Flame />
          <p className="mt-3 text-sm font-semibold">{t("public.invalid")}</p>
          <p className="mt-1 text-xs text-ink-soft">{t("public.invalidHint")}</p>
        </div>
      </div>
    );
  }

  const countryValues = new Map<string, number>(
    (countries.data ?? [])
      .filter((row) => typeof row.country === "string" && row.country !== "")
      .map((row) => [String(row.country), row.value ?? 0]),
  );

  return (
    <div className="min-h-screen bg-paper">
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-8">
        <header className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex items-center gap-2">
            <Flame />
            <h1 className="font-display text-xl font-bold tracking-tight">
              {t("public.title")}
            </h1>
          </div>
          <span className="text-xs text-ink-soft">{t("public.last30d")}</span>
        </header>
        <div className="rounded-lg border border-line bg-surface p-4">
          <div className="tnum font-display text-3xl font-bold">
            {formatNumber(visitors.data?.[0]?.value ?? 0)}
          </div>
          <div className="text-xs text-ink-soft">{t("metric.visitors")}</div>
        </div>
        <Panel title={t("web.geo")}>
          <Choropleth
            values={countryValues}
            selected={null}
            formatValue={formatNumber}
            legendLabel={t("metric.visitors")}
          />
        </Panel>
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title={t("web.topPages")}>
            <RankedTable rows={pages.data} dimension="page" />
          </Panel>
          <Panel title={t("web.country")}>
            <RankedTable rows={countries.data} dimension="country" />
          </Panel>
        </div>
        <p className="text-center text-[11px] text-ink-soft">{t("public.poweredBy")}</p>
      </div>
    </div>
  );
}
