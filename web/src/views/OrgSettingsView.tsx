import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { CopyButton, FIELD, Panel, PRIMARY_BUTTON, ScreenSubtitle } from "../components/widgets";
import {
  createProject,
  createSource,
  issueIngestKey,
  issueReadKey,
  listKeys,
  listSources,
  revokeKey,
  type IssuedKey,
  type Source,
  type SourceType,
} from "../lib/api";
import { Link } from "react-router-dom";

import { docsUrl } from "../lib/docs";
import {
  MCP_ENDPOINT,
  integrationSnippet,
  mcpPluginCommands,
  mcpServersConfig,
} from "../lib/snippets";
import { useDashboard } from "../lib/state";
import { BillingSection, DigestSection, MembersSection, SharesSection, UsageSection } from "./OrgSettingsSections";

// creatable source kinds (issue #45: web or API; "app" arrives with the
// custom-events slice and has no paste-ready snippet yet)
const SOURCE_TYPES: SourceType[] = ["web", "api"];


/** The one and only time the plaintext is visible (the server keeps a hash). */
function IssuedKeyModal({
  issued,
  source,
  onClose,
}: {
  issued: IssuedKey;
  source: Source | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const snippet = source ? integrationSnippet(source.type, issued.key) : null;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/40 px-4">
      <div
        role="dialog"
        aria-label={t("settings.keyModalTitle")}
        className="w-full max-w-lg rounded-lg border border-line bg-surface-raised p-5 shadow-xl"
      >
        <h2 className="font-display text-base font-bold">{t("settings.keyModalTitle")}</h2>
        <p className="mt-1 text-sm text-down">{t("settings.keyModalWarning")}</p>
        <div className="mt-3 flex items-center gap-2">
          <code className="tnum min-w-0 flex-1 break-all rounded-md border border-line bg-paper px-2 py-1.5 text-xs">
            {issued.key}
          </code>
          <CopyButton text={issued.key} label={t("settings.copyKey")} />
        </div>
        {snippet && (
          <>
            <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-ink-soft">
              {t("settings.snippet")}
            </h3>
            <div className="mt-1 flex items-start gap-2">
              <pre className="min-w-0 flex-1 overflow-x-auto rounded-md border border-line bg-paper px-2 py-1.5 text-xs">
                {snippet}
              </pre>
              <CopyButton text={snippet} label={t("settings.copySnippet")} />
            </div>
          </>
        )}
        <div className="mt-4 text-right">
          <button onClick={onClose} className={PRIMARY_BUTTON}>
            {t("settings.close")}
          </button>
        </div>
      </div>
    </div>
  );
}

function SourcesPanel({
  projectId,
  onIssued,
}: {
  projectId: string;
  onIssued: (issued: IssuedKey, source: Source) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [type, setType] = useState<SourceType>("web");

  const sources = useQuery({
    queryKey: ["sources", projectId],
    queryFn: () => listSources(projectId),
  });

  const create = useMutation({
    mutationFn: () => createSource(projectId, { type, name }),
    onSuccess: () => {
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["sources", projectId] });
    },
  });

  const issue = useMutation({
    mutationFn: (source: Source) =>
      issueIngestKey(source.id, source.name).then((issued) => ({ issued, source })),
    onSuccess: ({ issued, source }) => {
      onIssued(issued, source);
      void queryClient.invalidateQueries({ queryKey: ["keys"] });
    },
  });

  return (
    <div>
      <ul className="divide-y divide-line/60">
        {(sources.data ?? []).map((source) => (
          <li key={source.id} className="flex items-center gap-3 py-2">
            <span className="rounded-full border border-line px-2 py-0.5 text-[11px] font-semibold uppercase text-ink-soft">
              {t(`settings.type.${source.type}`)}
            </span>
            <span className="min-w-0 flex-1 truncate text-sm">{source.name}</span>
            <button
              onClick={() => issue.mutate(source)}
              className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-flame hover:text-flame"
            >
              {t("settings.issueIngestKey")}
            </button>
          </li>
        ))}
        {sources.data && sources.data.length === 0 && (
          <li className="py-3 text-sm text-ink-soft">{t("settings.noSources")}</li>
        )}
      </ul>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("settings.sourceName")}
          aria-label={t("settings.sourceName")}
          className={`min-w-0 flex-1 ${FIELD}`}
        />
        <select
          value={type}
          onChange={(event) => setType(event.target.value as SourceType)}
          aria-label={t("settings.sourceType")}
          className={FIELD}
        >
          {SOURCE_TYPES.map((option) => (
            <option key={option} value={option}>
              {t(`settings.type.${option}`)}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={name.trim() === ""}
          className={PRIMARY_BUTTON}
        >
          {t("settings.addSource")}
        </button>
      </form>
    </div>
  );
}

function ProjectsSection({
  orgId,
  onIssued,
}: {
  orgId: string;
  onIssued: (issued: IssuedKey, source: Source) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { projects } = useDashboard();
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");

  const create = useMutation({
    mutationFn: () => createProject(orgId, { slug, name }),
    onSuccess: (project) => {
      setName("");
      setSlug("");
      setSelected(project.id);
      void queryClient.invalidateQueries({ queryKey: ["projects", orgId] });
    },
  });

  return (
    <Panel title={t("settings.projects")}>
      <ul className="divide-y divide-line/60">
        {projects.map((project) => (
          <li key={project.id}>
            <button
              onClick={() => setSelected(selected === project.id ? null : project.id)}
              aria-expanded={selected === project.id}
              className="flex w-full items-center gap-3 py-2 text-left hover:text-flame"
            >
              <span className="flex-1 text-sm font-semibold">{project.name}</span>
              <span className="tnum text-xs text-ink-soft">{project.slug}</span>
            </button>
            {selected === project.id && (
              <div className="mb-2 rounded-md border border-line bg-paper px-3 py-2">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-soft">
                  {t("settings.sources")}
                </h3>
                <SourcesPanel projectId={project.id} onIssued={onIssued} />
              </div>
            )}
          </li>
        ))}
      </ul>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("settings.projectName")}
          aria-label={t("settings.projectName")}
          className={`min-w-0 flex-1 ${FIELD}`}
        />
        <input
          value={slug}
          onChange={(event) => setSlug(event.target.value)}
          placeholder={t("settings.projectSlug")}
          aria-label={t("settings.projectSlug")}
          className={`w-36 ${FIELD}`}
        />
        <button
          type="submit"
          disabled={name.trim() === "" || slug.trim() === ""}
          className={PRIMARY_BUTTON}
        >
          {t("settings.createProject")}
        </button>
      </form>
    </Panel>
  );
}

function KeysSection({
  orgId,
  onIssued,
}: {
  orgId: string;
  onIssued: (issued: IssuedKey) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const keys = useQuery({
    queryKey: ["keys", orgId],
    queryFn: () => listKeys(orgId),
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["keys"] });

  const issue = useMutation({
    mutationFn: () => issueReadKey(orgId, name),
    onSuccess: (issued) => {
      setName("");
      onIssued(issued);
      invalidate();
    },
  });

  const revoke = useMutation({ mutationFn: revokeKey, onSuccess: invalidate });

  return (
    <Panel title={t("settings.keys")}>
      <ul className="divide-y divide-line/60">
        {(keys.data ?? []).map((key) => (
          <li key={key.id} className="flex items-center gap-3 py-2">
            <code className="tnum text-xs">{key.key_prefix}…</code>
            <span className="rounded-full border border-line px-2 py-0.5 text-[11px] font-semibold uppercase text-ink-soft">
              {t(`settings.scope.${key.scope}`)}
            </span>
            <span className="min-w-0 flex-1 truncate text-sm text-ink-soft">{key.name}</span>
            {key.revoked ? (
              <span className="text-xs font-semibold text-down">{t("settings.revoked")}</span>
            ) : (
              <button
                onClick={() => revoke.mutate(key.id)}
                className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-down hover:text-down"
              >
                {t("settings.revoke")}
              </button>
            )}
          </li>
        ))}
        {keys.data && keys.data.length === 0 && (
          <li className="py-3 text-sm text-ink-soft">{t("settings.noKeys")}</li>
        )}
      </ul>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          issue.mutate();
        }}
      >
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("settings.keyName")}
          aria-label={t("settings.keyName")}
          className={`min-w-0 flex-1 ${FIELD}`}
        />
        <button type="submit" disabled={name.trim() === ""} className={PRIMARY_BUTTON}>
          {t("settings.issueReadKey")}
        </button>
      </form>
    </Panel>
  );
}

/** Connect Oriflux's read-only MCP server to Claude Code / Desktop / any agent.
 *  Everything shown is public config — the read key stays the user's, issued
 *  above and pasted in at install time; nothing here embeds a secret. */
function ConnectClaudeSection() {
  const { t } = useTranslation();
  return (
    <Panel title={t("settings.mcp.title")}>
      <p className="text-sm text-ink-soft">{t("settings.mcp.intro")}</p>

      <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-ink-soft">
        {t("settings.mcp.endpointLabel")}
      </h3>
      <div className="mt-1 flex items-center gap-2">
        <code className="min-w-0 flex-1 break-all rounded-md border border-line bg-paper px-2 py-1.5 text-xs">
          {MCP_ENDPOINT}
        </code>
        <CopyButton text={MCP_ENDPOINT} label={t("settings.mcp.copyEndpoint")} />
      </div>

      <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-ink-soft">
        {t("settings.mcp.pluginLabel")}
      </h3>
      <p className="mt-1 text-sm text-ink-soft">{t("settings.mcp.pluginHint")}</p>
      <div className="mt-1 flex items-start gap-2">
        <pre className="min-w-0 flex-1 overflow-x-auto rounded-md border border-line bg-paper px-2 py-1.5 text-xs">
          {mcpPluginCommands}
        </pre>
        <CopyButton text={mcpPluginCommands} label={t("settings.mcp.copyCommands")} />
      </div>

      <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-ink-soft">
        {t("settings.mcp.manualLabel")}
      </h3>
      <p className="mt-1 text-sm text-ink-soft">{t("settings.mcp.manualHint")}</p>
      <div className="mt-1 flex items-start gap-2">
        <pre className="min-w-0 flex-1 overflow-x-auto rounded-md border border-line bg-paper px-2 py-1.5 text-xs">
          {mcpServersConfig()}
        </pre>
        <CopyButton text={mcpServersConfig()} label={t("settings.mcp.copyConfig")} />
      </div>

      <p className="mt-3">
        <Link
          to={docsUrl("api-mcp")}
          className="text-xs font-medium text-flame underline-offset-2 hover:underline"
        >
          {t("settings.mcp.docsLink")}
        </Link>
      </p>
    </Panel>
  );
}

export default function OrgSettingsView() {
  const { t } = useTranslation();
  const { orgId } = useDashboard();
  const [issued, setIssued] = useState<{ issued: IssuedKey; source: Source | null } | null>(
    null,
  );

  if (orgId === null) return null; // session still resolving

  return (
    <div className="space-y-4">
      <h1 className="font-display text-xl font-bold tracking-tight">
        {t("nav.orgSettings")}
      </h1>
      <ScreenSubtitle id="orgSettings" />
      <UsageSection orgId={orgId} />
      <BillingSection orgId={orgId} />
      <ProjectsSection
        orgId={orgId}
        onIssued={(key, source) => setIssued({ issued: key, source })}
      />
      <KeysSection orgId={orgId} onIssued={(key) => setIssued({ issued: key, source: null })} />
      <ConnectClaudeSection />
      <MembersSection orgId={orgId} />
      <DigestSection orgId={orgId} />
      <SharesSection />
      {issued && (
        <IssuedKeyModal
          issued={issued.issued}
          source={issued.source}
          onClose={() => setIssued(null)}
        />
      )}
    </div>
  );
}
