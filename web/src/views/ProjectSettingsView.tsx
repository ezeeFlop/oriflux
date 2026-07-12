/** Project settings (issues #57 + #58): revenue connectors (Stripe /
 *  Lemon Squeezy webhooks — the secret is written once, never read back)
 *  and the Zeus infra mapping. Fills the last ComingSoon of the target IA. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { FIELD, Panel, PRIMARY_BUTTON } from "../components/widgets";
import {
  ApiError,
  createConnector,
  deleteConnector,
  fetchInfra,
  getZeusMapping,
  listConnectors,
  setZeusMapping,
  type Connector,
} from "../lib/api";

const CHIP =
  "rounded-full border border-line px-2 py-0.5 text-[11px] font-semibold uppercase text-ink-soft";

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

function ConnectorsPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState<Connector["provider"]>("stripe");
  const [secret, setSecret] = useState("");
  const [disabled, setDisabled] = useState(false);

  const connectors = useQuery({
    queryKey: ["connectors", projectId],
    queryFn: () => listConnectors(projectId),
  });
  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ["connectors", projectId] });

  const create = useMutation({
    mutationFn: () => createConnector(projectId, { provider, webhook_secret: secret }),
    onSuccess: () => {
      setSecret("");
      invalidate();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 503) setDisabled(true);
    },
  });
  const remove = useMutation({ mutationFn: deleteConnector, onSuccess: invalidate });

  return (
    <Panel title={t("projectSettings.connectors")}>
      <p className="text-xs text-ink-soft">{t("projectSettings.connectorsHint")}</p>
      <ul className="mt-2 divide-y divide-line/60">
        {(connectors.data ?? []).map((connector) => (
          <li key={connector.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
            <span className={CHIP}>{connector.provider}</span>
            <code className="tnum min-w-0 flex-1 truncate text-xs">
              {connector.webhook_path}
            </code>
            <CopyButton text={connector.webhook_path} label={t("projectSettings.copyWebhook")} />
            <button
              onClick={() => remove.mutate(connector.id)}
              aria-label={t("projectSettings.deleteConnector")}
              className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-down hover:text-down"
            >
              ✕
            </button>
          </li>
        ))}
        {connectors.data && connectors.data.length === 0 && (
          <li className="py-3 text-sm text-ink-soft">{t("projectSettings.noConnectors")}</li>
        )}
      </ul>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <select
          value={provider}
          onChange={(event) => setProvider(event.target.value as Connector["provider"])}
          aria-label={t("projectSettings.provider")}
          className={FIELD}
        >
          <option value="stripe">Stripe</option>
          <option value="lemonsqueezy">Lemon Squeezy</option>
        </select>
        <input
          type="password"
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          placeholder={t("projectSettings.webhookSecret")}
          aria-label={t("projectSettings.webhookSecret")}
          className={`min-w-0 flex-1 ${FIELD}`}
        />
        <button type="submit" disabled={secret.trim().length < 8} className={PRIMARY_BUTTON}>
          {t("projectSettings.addConnector")}
        </button>
      </form>
      <p className="mt-2 text-[11px] text-ink-soft">{t("projectSettings.secretOnce")}</p>
      {disabled && (
        <p className="mt-2 text-xs text-down">{t("projectSettings.connectorsDisabled")}</p>
      )}
    </Panel>
  );
}

function ZeusPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [service, setService] = useState<string | null>(null);

  const mapping = useQuery({
    queryKey: ["zeus", projectId],
    queryFn: () => getZeusMapping(projectId),
  });
  const infra = useQuery({
    queryKey: ["infra", projectId],
    queryFn: () => fetchInfra(projectId),
    refetchInterval: 30_000,
  });

  const save = useMutation({
    mutationFn: (value: string | null) => setZeusMapping(projectId, value),
    onSuccess: () => {
      setService(null);
      void queryClient.invalidateQueries({ queryKey: ["zeus", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["infra", projectId] });
    },
  });

  const current = mapping.data?.zeus_service ?? null;
  const value = service ?? current ?? "";

  return (
    <Panel title={t("projectSettings.zeus")}>
      <p className="text-xs text-ink-soft">{t("projectSettings.zeusHint")}</p>
      <form
        className="mt-2 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(value.trim() === "" ? null : value.trim());
        }}
      >
        <input
          value={value}
          onChange={(event) => setService(event.target.value)}
          placeholder="spt-oriflux_api"
          aria-label={t("projectSettings.zeusService")}
          className={`min-w-0 flex-1 ${FIELD}`}
        />
        <button type="submit" className={PRIMARY_BUTTON}>
          {t("projectSettings.zeusSave")}
        </button>
        {current !== null && (
          <button
            type="button"
            onClick={() => save.mutate(null)}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-soft hover:border-down hover:text-down"
          >
            {t("projectSettings.zeusClear")}
          </button>
        )}
      </form>
      <div className="mt-3 text-sm">
        {infra.data?.available ? (
          <p className="flex flex-wrap items-center gap-3">
            <span className="text-up" aria-hidden>
              ●
            </span>
            <span className="font-semibold">{String(infra.data.service)}</span>
            <span className="tnum">{infra.data.cpu_percent?.toFixed(1)} % CPU</span>
            <span className="tnum">{Math.round(infra.data.memory_mb ?? 0)} MB RAM</span>
            <span className="tnum">
              {String(infra.data.containers)} {t("infra.containers")}
            </span>
          </p>
        ) : (
          <p className="text-xs text-ink-soft">
            {current === null
              ? t("projectSettings.zeusUnset")
              : t("projectSettings.zeusUnavailable")}
          </p>
        )}
      </div>
    </Panel>
  );
}

export default function ProjectSettingsView() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();
  return (
    <div className="space-y-4">
      <h1 className="font-display text-xl font-bold tracking-tight">
        {t("nav.projectSettings")}
      </h1>
      <ConnectorsPanel projectId={projectId} />
      <ZeusPanel projectId={projectId} />
    </div>
  );
}
