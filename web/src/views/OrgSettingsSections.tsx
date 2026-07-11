/** Settings org, second slice (issue #46): members, the member's own digest
 *  subscription, and public share links. Rendered by OrgSettingsView. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { FIELD, Panel, PRIMARY_BUTTON } from "../components/widgets";
import {
  addMember,
  createCheckout,
  createPortal,
  getBilling,
  getUsage,
  getDigestPref,
  listMembers,
  listShares,
  mintShare,
  revokeShare,
  setDigestPref,
  unsubscribeDigest,
  type DigestPref,
  type MintedShare,
  type Role,
} from "../lib/api";
import { redirectTo } from "../lib/redirect";
import { useDashboard } from "../lib/state";

const CHIP =
  "rounded-full border border-line px-2 py-0.5 text-[11px] font-semibold uppercase text-ink-soft";

const ROLES: Role[] = ["viewer", "admin", "owner"];
const CADENCES: DigestPref["cadence"][] = ["weekly", "monthly"];
const DIGEST_LANGUAGES: DigestPref["language"][] = ["fr", "en", "es"];

export function UsageSection({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const usage = useQuery({
    queryKey: ["usage", orgId],
    queryFn: () => getUsage(orgId),
    refetchInterval: 60_000,
  });
  const data = usage.data;
  if (!data) return null;
  const pct = data.pct;
  return (
    <Panel title={t("settings.usage")}>
      <div className="flex flex-wrap items-baseline gap-3">
        <span className={CHIP}>{data.plan_name ?? data.plan_slug}</span>
        <span className="tnum text-sm">
          {data.used.toLocaleString()}
          {data.monthly_events !== null && ` / ${data.monthly_events.toLocaleString()}`}
        </span>
        <span className="text-xs text-ink-soft">{t("settings.usageEvents")}</span>
        {pct !== null && (
          <span className={`tnum text-xs font-semibold ${pct >= 80 ? "text-down" : "text-ink-soft"}`}>
            {pct} %
          </span>
        )}
      </div>
      {pct !== null ? (
        <div className="mt-2 h-2 rounded-full bg-line">
          <div
            className={`h-2 rounded-full ${pct >= 80 ? "bg-down" : "bg-flame"}`}
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        </div>
      ) : (
        <p className="mt-2 text-xs text-ink-soft">{t("settings.usageUnlimited")}</p>
      )}
    </Panel>
  );
}

export function BillingSection({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const billing = useQuery({
    queryKey: ["billing", orgId],
    queryFn: () => getBilling(orgId),
  });
  const checkout = useMutation({
    mutationFn: (planSlug: string) => createCheckout(orgId, planSlug),
    onSuccess: ({ url }) => redirectTo(url),
  });
  const portal = useMutation({
    mutationFn: () => createPortal(orgId),
    onSuccess: ({ url }) => redirectTo(url),
  });

  const data = billing.data;
  if (!data?.enabled) return null; // keyless instance: billing stays invisible

  const upgrades = data.plans.filter((p) => p.subscribable && p.slug !== data.plan_slug);

  return (
    <Panel title={t("settings.billing")}>
      <ul className="divide-y divide-line/60">
        {upgrades.map((plan) => (
          <li key={plan.slug} className="flex items-center gap-3 py-2 text-sm">
            <span className={CHIP}>{plan.name}</span>
            <span className="min-w-0 flex-1 text-ink-soft">
              {plan.monthly_events !== null
                ? t("settings.planQuota", { quota: plan.monthly_events.toLocaleString() })
                : t("settings.usageUnlimited")}
            </span>
            <button onClick={() => checkout.mutate(plan.slug)} className={PRIMARY_BUTTON}>
              {t("settings.subscribe", { plan: plan.name })}
            </button>
          </li>
        ))}
        {upgrades.length === 0 && (
          <li className="py-3 text-sm text-ink-soft">{t("settings.noUpgrades")}</li>
        )}
      </ul>
      {data.has_customer && (
        <button
          onClick={() => portal.mutate()}
          className="mt-3 rounded-md border border-line px-3 py-1.5 text-sm text-ink-soft hover:border-flame hover:text-flame"
        >
          {t("settings.manageSubscription")}
        </button>
      )}
      {(checkout.isError || portal.isError) && (
        <p className="mt-2 text-xs text-down">{t("common.error")}</p>
      )}
    </Panel>
  );
}

export function MembersSection({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("viewer");

  const members = useQuery({
    queryKey: ["members", orgId],
    queryFn: () => listMembers(orgId),
  });

  const invite = useMutation({
    mutationFn: () => addMember(orgId, { email, role }),
    onSuccess: () => {
      setEmail("");
      void queryClient.invalidateQueries({ queryKey: ["members", orgId] });
    },
  });

  return (
    <Panel title={t("settings.members")}>
      <ul className="divide-y divide-line/60">
        {(members.data ?? []).map((member) => (
          <li key={member.user_id} className="flex items-center gap-3 py-2">
            <span className="min-w-0 flex-1 truncate text-sm">{member.email}</span>
            {member.name && (
              <span className="truncate text-xs text-ink-soft">{member.name}</span>
            )}
            <span className={CHIP}>{t(`settings.role.${member.role}`)}</span>
          </li>
        ))}
      </ul>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          invite.mutate();
        }}
      >
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder={t("settings.memberEmail")}
          aria-label={t("settings.memberEmail")}
          className={`min-w-0 flex-1 ${FIELD}`}
        />
        <select
          value={role}
          onChange={(event) => setRole(event.target.value as Role)}
          aria-label={t("settings.memberRole")}
          className={FIELD}
        >
          {ROLES.map((option) => (
            <option key={option} value={option}>
              {t(`settings.role.${option}`)}
            </option>
          ))}
        </select>
        <button type="submit" disabled={email.trim() === ""} className={PRIMARY_BUTTON}>
          {t("settings.invite")}
        </button>
      </form>
      {invite.isError && (
        <p className="mt-2 text-xs text-down">{t("settings.inviteFailed")}</p>
      )}
    </Panel>
  );
}

export function DigestSection({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [cadence, setCadence] = useState<DigestPref["cadence"]>("weekly");
  const [language, setLanguage] = useState<DigestPref["language"]>("fr");

  const pref = useQuery({
    queryKey: ["digest", orgId],
    queryFn: () => getDigestPref(orgId),
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["digest", orgId] });
  const save = useMutation({
    mutationFn: () => setDigestPref(orgId, { cadence, language }),
    onSuccess: invalidate,
  });
  const unsubscribe = useMutation({
    mutationFn: () => unsubscribeDigest(orgId),
    onSuccess: invalidate,
  });

  const subscribed = pref.data != null;

  return (
    <Panel title={t("settings.digest")}>
      <p className="text-sm text-ink-soft">
        {subscribed
          ? t("settings.digestActive", {
              cadence: t(`settings.cadence.${pref.data?.cadence}`),
              language: pref.data?.language.toUpperCase(),
            })
          : t("settings.digestOff")}
      </p>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <select
          value={cadence}
          onChange={(event) => setCadence(event.target.value as DigestPref["cadence"])}
          aria-label={t("settings.digestCadence")}
          className={FIELD}
        >
          {CADENCES.map((option) => (
            <option key={option} value={option}>
              {t(`settings.cadence.${option}`)}
            </option>
          ))}
        </select>
        <select
          value={language}
          onChange={(event) => setLanguage(event.target.value as DigestPref["language"])}
          aria-label={t("settings.digestLanguage")}
          className={FIELD}
        >
          {DIGEST_LANGUAGES.map((option) => (
            <option key={option} value={option}>
              {option.toUpperCase()}
            </option>
          ))}
        </select>
        <button type="submit" className={PRIMARY_BUTTON}>
          {t("settings.digestSubscribe")}
        </button>
        {subscribed && (
          <button
            type="button"
            onClick={() => unsubscribe.mutate()}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-soft hover:border-down hover:text-down"
          >
            {t("settings.digestUnsubscribe")}
          </button>
        )}
      </form>
    </Panel>
  );
}

/** The full URL is copyable here and never again (the server keeps a hash). */
function ShareLinkModal({ share, onClose }: { share: MintedShare; onClose: () => void }) {
  const { t } = useTranslation();
  const url = `${window.location.origin}${share.public_path}`;
  const [copied, setCopied] = useState(false);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/40 px-4">
      <div
        role="dialog"
        aria-label={t("settings.shareModalTitle")}
        className="w-full max-w-lg rounded-lg border border-line bg-surface-raised p-5 shadow-xl"
      >
        <h2 className="font-display text-base font-bold">{t("settings.shareModalTitle")}</h2>
        <p className="mt-1 text-sm text-down">{t("settings.shareModalWarning")}</p>
        <div className="mt-3 flex items-center gap-2">
          <code className="tnum min-w-0 flex-1 break-all rounded-md border border-line bg-paper px-2 py-1.5 text-xs">
            {url}
          </code>
          <button
            onClick={() => {
              void navigator.clipboard?.writeText(url);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
            aria-label={t("settings.copyLink")}
            className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-flame hover:text-flame"
          >
            {copied ? t("settings.copied") : t("settings.copy")}
          </button>
        </div>
        <div className="mt-4 text-right">
          <button onClick={onClose} className={PRIMARY_BUTTON}>
            {t("settings.close")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function SharesSection() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { projects } = useDashboard();
  const [projectId, setProjectId] = useState<string>("");
  const [minted, setMinted] = useState<MintedShare | null>(null);

  const effectiveProject = projectId || projects[0]?.id || "";

  const shares = useQuery({
    queryKey: ["shares", effectiveProject],
    queryFn: () => listShares(effectiveProject),
    enabled: effectiveProject !== "",
  });

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ["shares", effectiveProject] });

  const mint = useMutation({
    mutationFn: () => mintShare(effectiveProject),
    onSuccess: (share) => {
      setMinted(share);
      invalidate();
    },
  });

  const revoke = useMutation({ mutationFn: revokeShare, onSuccess: invalidate });

  return (
    <Panel
      title={t("settings.shares")}
      actions={
        <select
          value={effectiveProject}
          onChange={(event) => setProjectId(event.target.value)}
          aria-label={t("common.project")}
          className={FIELD}
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      }
    >
      <ul className="divide-y divide-line/60">
        {(shares.data ?? []).map((share) => (
          <li key={share.id} className="flex items-center gap-3 py-2">
            <span className="tnum text-xs text-ink-soft">
              {new Date(share.created_at).toLocaleDateString(i18n.language)}
            </span>
            <code className="tnum min-w-0 flex-1 truncate text-xs">{share.id}</code>
            {share.revoked ? (
              <span className="text-xs font-semibold text-down">{t("settings.revoked")}</span>
            ) : (
              <button
                onClick={() => revoke.mutate(share.id)}
                className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-down hover:text-down"
              >
                {t("settings.revoke")}
              </button>
            )}
          </li>
        ))}
        {shares.data && shares.data.length === 0 && (
          <li className="py-3 text-sm text-ink-soft">{t("settings.noShares")}</li>
        )}
      </ul>
      <div className="mt-3">
        <button
          onClick={() => mint.mutate()}
          disabled={effectiveProject === ""}
          className={PRIMARY_BUTTON}
        >
          {t("settings.createShare")}
        </button>
      </div>
      {minted && <ShareLinkModal share={minted} onClose={() => setMinted(null)} />}
    </Panel>
  );
}
