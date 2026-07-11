/** Self-serve onboarding (issue #62): a signed-in user without any
 *  organization never sees an empty dashboard — this flow creates the org,
 *  then walks the zero-terminal path (project → source → key → snippet)
 *  and watches, through the standard query contract, for the very first
 *  event to arrive before opening the portfolio. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";

import { FIELD, PRIMARY_BUTTON } from "../components/widgets";
import {
  apiFetch,
  auth,
  createProject,
  createSource,
  fetchMe,
  issueIngestKey,
  runQuery,
  type IssuedKey,
  type Project,
  type Source,
  type SourceType,
} from "../lib/api";
import { integrationSnippet } from "../lib/snippets";
import { lastMinutes } from "../lib/periods";

type Step = "org" | "project" | "source" | "integrate";

function CopyButton({ text, label }: { text: string; label: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        void navigator.clipboard?.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      aria-label={label}
      className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-flame hover:text-flame"
    >
      {copied ? t("settings.copied") : t("settings.copy")}
    </button>
  );
}

function Flame() {
  return (
    <svg viewBox="0 0 24 24" className="h-8 w-8 text-flame" fill="currentColor" aria-hidden>
      <path d="M4 3h13l-2.5 3.5L17 10H6v11a2 2 0 0 1-2-2V3z" />
    </svg>
  );
}

function FirstEventWatch({ project }: { project: Project }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const probe = useQuery({
    queryKey: ["first-event", project.id],
    queryFn: () =>
      runQuery({
        metric: "pageviews",
        filters: [{ dimension: "project_id", op: "eq", value: project.id }],
        period: lastMinutes(60),
      }),
    refetchInterval: 5000,
  });
  const received = (probe.data?.results?.[0]?.value ?? 0) > 0;
  return (
    <div className="mt-4 rounded-md border border-line bg-paper p-3">
      {received ? (
        <>
          <p className="text-sm font-semibold text-up">{t("welcome.firstEventReceived")}</p>
          <button onClick={() => navigate("/")} className={`mt-3 ${PRIMARY_BUTTON}`}>
            {t("welcome.openPortfolio")}
          </button>
        </>
      ) : (
        <>
          <p className="text-sm text-ink-soft">
            <span className="mr-2 inline-block animate-pulse text-flame" aria-hidden>
              ●
            </span>
            {t("welcome.waitingFirstEvent")}
          </p>
          <button
            onClick={() => navigate("/")}
            className="mt-3 text-xs text-ink-soft underline hover:text-flame"
          >
            {t("welcome.skip")}
          </button>
        </>
      )}
    </div>
  );
}

export default function WelcomeView() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe });

  const [step, setStep] = useState<Step>("org");
  const [orgName, setOrgName] = useState("");
  const [orgSlug, setOrgSlug] = useState("");
  const [orgId, setOrgId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");
  const [projectSlug, setProjectSlug] = useState("");
  const [project, setProject] = useState<Project | null>(null);
  const [sourceName, setSourceName] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("web");
  const [source, setSource] = useState<Source | null>(null);
  const [issued, setIssued] = useState<IssuedKey | null>(null);

  const createOrg = useMutation({
    mutationFn: () =>
      apiFetch<{ id: string }>("/api/v1/orgs", {
        method: "POST",
        body: JSON.stringify({ slug: orgSlug, name: orgName }),
      }),
    onSuccess: (org) => {
      auth.orgId = org.id;
      setOrgId(org.id);
      setStep("project");
      void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });

  const createProjectStep = useMutation({
    mutationFn: () => createProject(orgId as string, { slug: projectSlug, name: projectName }),
    onSuccess: (created) => {
      setProject(created);
      setStep("source");
    },
  });

  const createSourceStep = useMutation({
    mutationFn: () =>
      createSource((project as Project).id, { type: sourceType, name: sourceName }),
    onSuccess: async (created) => {
      setSource(created);
      const key = await issueIngestKey(created.id, created.name);
      setIssued(key);
      setStep("integrate");
    },
  });

  // an invited member already has an org: straight to the portfolio
  if (step === "org" && me.data && me.data.orgs.length > 0) {
    return <Navigate to="/" replace />;
  }

  const snippet = source && issued ? integrationSnippet(source.type, issued.key) : null;

  return (
    <div className="flex min-h-screen items-start justify-center bg-paper px-4 pt-[10vh]">
      <div className="w-full max-w-xl rounded-lg border border-line bg-surface p-6">
        <div className="flex items-center gap-3">
          <Flame />
          <div>
            <h1 className="font-display text-xl font-bold tracking-tight">
              {t("welcome.title")}
            </h1>
            <p className="text-sm text-ink-soft">{t(`welcome.step.${step}`)}</p>
          </div>
        </div>

        {step === "org" && (
          <form
            className="mt-5 space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              createOrg.mutate();
            }}
          >
            <input
              value={orgName}
              onChange={(event) => setOrgName(event.target.value)}
              placeholder={t("welcome.orgName")}
              aria-label={t("welcome.orgName")}
              className={`w-full ${FIELD}`}
            />
            <input
              value={orgSlug}
              onChange={(event) => setOrgSlug(event.target.value)}
              placeholder={t("settings.projectSlug")}
              aria-label={t("welcome.orgSlug")}
              className={`w-full ${FIELD}`}
            />
            <button
              type="submit"
              disabled={orgName.trim() === "" || orgSlug.trim() === ""}
              className={PRIMARY_BUTTON}
            >
              {t("welcome.createOrg")}
            </button>
            {createOrg.isError && (
              <p className="text-xs text-down">{t("welcome.orgFailed")}</p>
            )}
          </form>
        )}

        {step === "project" && (
          <form
            className="mt-5 space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              createProjectStep.mutate();
            }}
          >
            <input
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              placeholder={t("settings.projectName")}
              aria-label={t("settings.projectName")}
              className={`w-full ${FIELD}`}
            />
            <input
              value={projectSlug}
              onChange={(event) => setProjectSlug(event.target.value)}
              placeholder={t("settings.projectSlug")}
              aria-label={t("welcome.projectSlug")}
              className={`w-full ${FIELD}`}
            />
            <button
              type="submit"
              disabled={projectName.trim() === "" || projectSlug.trim() === ""}
              className={PRIMARY_BUTTON}
            >
              {t("settings.createProject")}
            </button>
          </form>
        )}

        {step === "source" && (
          <form
            className="mt-5 flex flex-wrap items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              createSourceStep.mutate();
            }}
          >
            <input
              value={sourceName}
              onChange={(event) => setSourceName(event.target.value)}
              placeholder={t("settings.sourceName")}
              aria-label={t("settings.sourceName")}
              className={`min-w-0 flex-1 ${FIELD}`}
            />
            <select
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value as SourceType)}
              aria-label={t("settings.sourceType")}
              className={FIELD}
            >
              <option value="web">{t("settings.type.web")}</option>
              <option value="api">{t("settings.type.api")}</option>
            </select>
            <button
              type="submit"
              disabled={sourceName.trim() === ""}
              className={PRIMARY_BUTTON}
            >
              {t("settings.addSource")}
            </button>
          </form>
        )}

        {step === "integrate" && issued && (
          <div className="mt-5">
            <p className="text-sm text-down">{t("settings.keyModalWarning")}</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="tnum min-w-0 flex-1 break-all rounded-md border border-line bg-paper px-2 py-1.5 text-xs">
                {issued.key}
              </code>
              <CopyButton text={issued.key} label={t("settings.copyKey")} />
            </div>
            {snippet && (
              <div className="mt-3 flex items-start gap-2">
                <pre className="min-w-0 flex-1 overflow-x-auto rounded-md border border-line bg-paper px-2 py-1.5 text-xs">
                  {snippet}
                </pre>
                <CopyButton text={snippet} label={t("settings.copySnippet")} />
              </div>
            )}
            {project && <FirstEventWatch project={project} />}
          </div>
        )}
      </div>
    </div>
  );
}
