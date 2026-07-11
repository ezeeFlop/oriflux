import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { LANGUAGES, setLanguage, type Language } from "../i18n";
import { PROJECT_SECTIONS } from "../lib/sections";
import { useDashboard } from "../lib/state";
import { PERIOD_KEYS, type PeriodKey } from "../lib/periods";

type LinkClass = (state: { isActive: boolean }) => string;

/** Section links inside a project — shared by the sidebar and mobile nav;
 *  the query string travels so period/compare survive navigation. */
function SectionLinks({ projectId, linkClass }: { projectId: string; linkClass: LinkClass }) {
  const { t } = useTranslation();
  const { search } = useLocation();
  return (
    <>
      {PROJECT_SECTIONS.map(({ key, path }) => (
        <NavLink
          key={key}
          to={{ pathname: `/p/${projectId}/${path}`, search }}
          className={linkClass}
        >
          {t(`nav.${key}`)}
        </NavLink>
      ))}
    </>
  );
}

/** Project links on the portfolio level — shared by the sidebar and mobile nav. */
function ProjectLinks({ linkClass }: { linkClass: LinkClass }) {
  const { projects } = useDashboard();
  const { search } = useLocation();
  return (
    <>
      {projects.map((project) => (
        <NavLink
          key={project.id}
          to={{ pathname: `/p/${project.id}/web`, search }}
          className={linkClass}
        >
          {project.name}
        </NavLink>
      ))}
    </>
  );
}

function Flame() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 text-flame" fill="currentColor" aria-hidden>
      <path d="M4 3h13l-2.5 3.5L17 10H6v11a2 2 0 0 1-2-2V3z" />
    </svg>
  );
}

const LANGUAGE_NAMES: Record<Language, string> = {
  fr: "Français",
  en: "English",
  es: "Español",
};

export function PeriodPicker() {
  const { t } = useTranslation();
  const { periodKey, setPeriodKey, compare, setCompare } = useDashboard();
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label={t("period.label")}>
      {PERIOD_KEYS.map((key: PeriodKey) => (
        <button
          key={key}
          onClick={() => setPeriodKey(key)}
          aria-pressed={periodKey === key}
          className={`rounded-md px-2 py-1 text-xs font-medium transition-colors ${
            periodKey === key
              ? "bg-flame text-white"
              : "text-ink-soft hover:bg-flame-soft hover:text-ink"
          }`}
        >
          {t(`period.${key}`)}
        </button>
      ))}
      <label className="ml-1 flex cursor-pointer items-center gap-1.5 text-xs text-ink-soft">
        <input
          type="checkbox"
          checked={compare}
          onChange={(event) => setCompare(event.target.checked)}
          className="accent-flame"
        />
        {t("period.compare")}
      </label>
    </div>
  );
}

function ThemeButton() {
  const { t } = useTranslation();
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const toggle = () => {
    const next = document.documentElement.classList.toggle("dark");
    localStorage.setItem("oriflux.theme", next ? "dark" : "light");
    setDark(next);
  };
  return (
    <button
      onClick={toggle}
      aria-label={t("common.theme")}
      className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm text-ink-soft hover:bg-flame-soft hover:text-ink"
    >
      <span>{t("common.theme")}</span>
      <span aria-hidden>{dark ? "☾" : "☀"}</span>
    </button>
  );
}

function AccountMenu() {
  const { t, i18n } = useTranslation();
  const { me, logout } = useDashboard();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { search } = useLocation();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const initial = (me?.name || me?.email || "?").slice(0, 1).toUpperCase();

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((value) => !value)}
        aria-label={t("account.label")}
        aria-expanded={open}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-flame-soft text-sm font-bold text-flame hover:brightness-95"
      >
        {initial}
      </button>
      {open && (
        <div className="absolute right-0 top-10 z-30 w-56 rounded-lg border border-line bg-surface-raised p-2 shadow-lg">
          <div className="border-b border-line px-2 pb-2">
            <p className="truncate text-sm font-semibold">{me?.name}</p>
            <p className="truncate text-xs text-ink-soft">{me?.email}</p>
          </div>
          <div className="mt-2 flex items-center gap-1 px-2" role="group" aria-label={t("common.language")}>
            {LANGUAGES.map((lang) => (
              <button
                key={lang}
                onClick={() => setLanguage(lang)}
                aria-label={LANGUAGE_NAMES[lang]}
                className={`rounded-md px-2 py-1 text-xs font-semibold uppercase ${
                  i18n.language === lang
                    ? "bg-flame text-white"
                    : "text-ink-soft hover:bg-flame-soft hover:text-ink"
                }`}
              >
                {lang}
              </button>
            ))}
          </div>
          <div className="mt-1">
            <ThemeButton />
            <button
              onClick={() => {
                setOpen(false);
                navigate({ pathname: "/settings/org", search });
              }}
              className="w-full rounded-md px-2 py-1.5 text-left text-sm text-ink-soft hover:bg-flame-soft hover:text-ink"
            >
              {t("nav.orgSettings")}
            </button>
            <button
              onClick={logout}
              className="w-full rounded-md px-2 py-1.5 text-left text-sm text-ink-soft hover:bg-flame-soft hover:text-flame"
            >
              {t("nav.logout")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SidebarNav() {
  const { t } = useTranslation();
  const { me, projects, orgId, setOrgId } = useDashboard();
  const { projectId } = useParams();
  const { search } = useLocation();
  const navigate = useNavigate();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center rounded-md px-2.5 py-1.5 text-sm transition-colors ${
      isActive ? "bg-flame-soft font-semibold text-flame" : "text-ink-soft hover:bg-flame-soft/60 hover:text-ink"
    }`;

  return (
    <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2 py-3">
      {me && me.orgs.length > 1 && (
        <select
          aria-label={t("common.organization")}
          value={orgId ?? ""}
          onChange={(event) => setOrgId(event.target.value)}
          className="mb-2 rounded-md border border-line bg-surface px-2 py-1 text-xs"
        >
          {me.orgs.map((membership) => (
            <option key={membership.org_id} value={membership.org_id}>
              {membership.org_id.slice(0, 8)}
            </option>
          ))}
        </select>
      )}

      <NavLink to={{ pathname: "/", search }} end className={linkClass}>
        {t("nav.home")}
      </NavLink>

      {projectId ? (
        <>
          <select
            aria-label={t("common.project")}
            value={projectId}
            onChange={(event) => navigate(`/p/${event.target.value}/web${search}`)}
            className="mb-1 mt-3 rounded-md border border-line bg-surface px-2 py-1 text-sm font-semibold"
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          <SectionLinks projectId={projectId} linkClass={linkClass} />
        </>
      ) : (
        <>
          <p className="mt-3 px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
            {t("nav.projects")}
          </p>
          <ProjectLinks linkClass={linkClass} />
        </>
      )}
    </nav>
  );
}

export default function Shell() {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-surface md:flex">
        <NavLink to="/" className="flex items-center gap-2 border-b border-line px-4 py-3">
          <Flame />
          <span className="font-display text-base font-bold tracking-tight">{t("app.name")}</span>
        </NavLink>
        <SidebarNav />
        <p className="border-t border-line px-4 py-2 text-[11px] text-ink-soft">
          {/* CC-BY 4.0 attribution required by the DB-IP Lite databases (#14) */}
          {t("footer.geoAttribution")}{" "}
          <a href="https://db-ip.com" target="_blank" rel="noreferrer" className="underline hover:text-ink">
            DB-IP
          </a>
        </p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-line bg-paper/90 backdrop-blur">
          <div className="flex flex-wrap items-center gap-3 px-4 py-2">
            <NavLink to="/" className="flex items-center gap-2 md:hidden">
              <Flame />
              <span className="font-display text-base font-bold tracking-tight">{t("app.name")}</span>
            </NavLink>
            <div className="ml-auto flex items-center gap-3">
              <PeriodPicker />
              <AccountMenu />
            </div>
          </div>
          {/* small screens: the sidebar collapses into a scrollable nav strip */}
          <div className="overflow-x-auto border-t border-line md:hidden">
            <div className="flex min-w-max gap-1 px-2 py-1.5">
              <MobileNav />
            </div>
          </div>
        </header>

        <main className="min-w-0 flex-1 px-4 py-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function MobileNav() {
  const { t } = useTranslation();
  const { projectId } = useParams();
  const { search } = useLocation();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `whitespace-nowrap rounded-md px-2.5 py-1 text-xs ${
      isActive ? "bg-flame-soft font-semibold text-flame" : "text-ink-soft"
    }`;

  return (
    <>
      <NavLink to={{ pathname: "/", search }} end className={linkClass}>
        {t("nav.home")}
      </NavLink>
      {projectId ? (
        <SectionLinks projectId={projectId} linkClass={linkClass} />
      ) : (
        <ProjectLinks linkClass={linkClass} />
      )}
    </>
  );
}
