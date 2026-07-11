/** Per-project live view (issue #53): the project's live counter comes from
 *  the org WebSocket channel; active pages/countries are project-scoped
 *  30-minute registry queries on the standard 10 s polling — the WS payload
 *  is org-wide by design, and a broken socket must never blank the view. */

import { useQueries } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { Panel, RankedTable } from "../components/widgets";
import WorldLive from "../components/WorldLive";
import { runQuery } from "../lib/api";
import { formatNumber } from "../lib/format";
import { lastMinutes } from "../lib/periods";
import { useDashboard } from "../lib/state";
import { useLive } from "../lib/useLive";

const LIVE_POLL_MS = 10_000;

export default function LiveView() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();
  const { projects } = useDashboard();
  const live = useLive();

  const projectFilter = [{ dimension: "project_id", op: "eq" as const, value: projectId }];
  const [pagesNow, countriesNow] = useQueries({
    queries: [
      {
        queryKey: ["live-pages", projectId],
        queryFn: () =>
          runQuery({
            metric: "visitors",
            dimensions: ["page"],
            filters: projectFilter,
            period: lastMinutes(30),
          }),
        refetchInterval: LIVE_POLL_MS,
      },
      {
        queryKey: ["live-countries", projectId],
        queryFn: () =>
          runQuery({
            metric: "visitors",
            dimensions: ["country"],
            filters: projectFilter,
            period: lastMinutes(30),
          }),
        refetchInterval: LIVE_POLL_MS,
      },
    ],
  });

  const liveCount = live?.projects.find((p) => p.id === projectId)?.live ?? null;
  const projectName = projects.find((p) => p.id === projectId)?.name ?? "";
  const countryRows = countriesNow.data?.results ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="font-display text-xl font-bold tracking-tight">
          {t("nav.live")} — {projectName}
        </h1>
        {live ? (
          <span className="text-[10px] uppercase text-up">ws</span>
        ) : (
          <span className="text-[10px] uppercase text-ink-soft">{t("live.polling")}</span>
        )}
      </div>

      <div className="flex items-baseline gap-2">
        <span className="tnum font-display text-4xl font-bold">
          {liveCount === null ? "–" : formatNumber(liveCount)}
        </span>
        <span className="text-sm text-ink-soft">{t("home.liveVisitors")}</span>
      </div>

      <Panel title={t("live.map")}>
        <WorldLive
          countries={countryRows.map((row) => ({
            country: String((row as { country?: unknown }).country ?? ""),
            value: Number(row.value ?? 0),
          }))}
        />
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title={t("home.topPagesNow")}>
          <RankedTable rows={pagesNow.data?.results} dimension="page" />
        </Panel>
        <Panel title={t("home.topCountriesNow")}>
          <RankedTable rows={countryRows} dimension="country" />
        </Panel>
      </div>
    </div>
  );
}
