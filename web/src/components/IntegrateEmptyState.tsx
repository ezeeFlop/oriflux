/** Actionable empty state for the Web and API screens (issue #70): when a
 *  project emitted nothing over the period, the screen hands the user the
 *  integration itself. Keys are hashed server-side (plaintext exists only
 *  at issuance), so "the real key" means issuing one inline: the button
 *  creates the source if needed, mints an ingest key, and reveals the
 *  ready-to-paste snippet. */

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import {
  createSource,
  issueIngestKey,
  listSources,
  type IssuedKey,
  type SourceType,
} from "../lib/api";
import { integrationSnippet } from "../lib/snippets";
import { CopyButton, DocsLink, PRIMARY_BUTTON } from "./widgets";

const DOCS_SLUGS: Record<string, string> = { web: "oriflux-js", api: "python-sdk" };

export default function IntegrateEmptyState({
  projectId,
  type,
}: {
  projectId: string;
  type: Extract<SourceType, "web" | "api">;
}) {
  const { t } = useTranslation();
  const [issued, setIssued] = useState<IssuedKey | null>(null);

  const sources = useQuery({
    queryKey: ["sources", projectId],
    queryFn: () => listSources(projectId),
  });

  const issue = useMutation({
    mutationFn: async () => {
      const existing = (sources.data ?? []).find((source) => source.type === type);
      const source =
        existing ?? (await createSource(projectId, { type, name: type === "web" ? "site" : "backend" }));
      return issueIngestKey(source.id, source.name);
    },
    onSuccess: setIssued,
  });

  const key = issued?.key ?? "ofx_ing_…";
  const snippet = integrationSnippet(type, key) ?? "";
  const block = type === "api" ? `pip install oriflux-sdk\n\n${snippet}` : snippet;

  return (
    <div className="rounded-xl border border-flame/40 bg-flame-soft/40 px-4 py-3">
      <p className="text-sm font-semibold">{t(`emptyState.${type}Title`)}</p>
      <p className="mt-1 text-sm text-ink-soft">{t(`emptyState.${type}Body`)}</p>
      <div className="mt-3 flex items-start gap-2">
        <pre className="min-w-0 flex-1 overflow-x-auto rounded-md border border-line bg-paper px-2 py-1.5 text-xs">
          {block}
        </pre>
        {issued && <CopyButton text={block} label={t("settings.copySnippet")} />}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {!issued && (
          <button onClick={() => issue.mutate()} disabled={issue.isPending} className={PRIMARY_BUTTON}>
            {t("emptyState.generate")}
          </button>
        )}
        {issued && <p className="text-xs text-down">{t("emptyState.keyOnce")}</p>}
        {issue.isError && <p className="text-xs text-down">{t("emptyState.issueFailed")}</p>}
        <DocsLink slug={DOCS_SLUGS[type]} />
      </div>
    </div>
  );
}
