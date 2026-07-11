/** Public dashboard (issue #41): no auth, a curated read-only subset for a
 *  single project served through a signed share token. Every number goes
 *  through /public/{token}/query — the server rejects anything outside the
 *  allow-list, so this page can only ever show the safe subset. */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
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

export default function PublicView() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const period = PERIOD();

  const visitors = useQuery({
    queryKey: ["pub-visitors", token],
    queryFn: () => publicQuery(token, { metric: "visitors", period }),
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
      <div className="paper-grain flex min-h-screen items-center justify-center">
        <p className="text-sm text-ink-soft">{t("public.invalid")}</p>
      </div>
    );
  }

  return (
    <div className="paper-grain min-h-screen">
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-8">
        <header className="flex items-baseline justify-between">
          <h1 className="font-display text-xl font-bold">{t("public.title")}</h1>
          <span className="text-xs text-ink-soft">{t("public.last30d")}</span>
        </header>
        <div className="rounded-xl border border-line bg-surface p-4">
          <div className="font-display text-3xl font-bold tabular-nums">
            {formatNumber(visitors.data?.[0]?.value ?? 0)}
          </div>
          <div className="text-xs text-ink-soft">{t("metric.visitors")}</div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title={t("web.topPages")}>
            <RankedTable rows={pages.data} dimension="page" />
          </Panel>
          <Panel title={t("web.geo")}>
            <RankedTable rows={countries.data} dimension="country" />
          </Panel>
        </div>
        <p className="text-center text-[11px] text-ink-soft">
          {t("public.poweredBy")}
        </p>
      </div>
    </div>
  );
}
