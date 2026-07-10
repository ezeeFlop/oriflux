import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { setLanguage } from "../i18n";
import { useDashboard } from "../lib/state";
import { PERIOD_KEYS, type PeriodKey } from "../lib/periods";

function Flame() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6 text-flame" fill="currentColor" aria-hidden>
      <path d="M4 3h13l-2.5 3.5L17 10H6v11a2 2 0 0 1-2-2V3z" />
    </svg>
  );
}

function ThemeToggle() {
  const { t } = useTranslation();
  const toggle = () => {
    const dark = document.documentElement.classList.toggle("dark");
    localStorage.setItem("oriflux.theme", dark ? "dark" : "light");
  };
  return (
    <button
      onClick={toggle}
      aria-label={t("common.theme")}
      className="rounded-md border border-line px-2 py-1 text-xs text-ink-soft hover:text-ink"
    >
      ◐
    </button>
  );
}

function LangToggle() {
  const { i18n, t } = useTranslation();
  const next = i18n.language === "fr" ? "en" : "fr";
  return (
    <button
      onClick={() => setLanguage(next)}
      aria-label={t("common.language")}
      className="rounded-md border border-line px-2 py-1 text-xs font-semibold uppercase text-ink-soft hover:text-ink"
    >
      {next}
    </button>
  );
}

export function PeriodPicker() {
  const { t } = useTranslation();
  const { periodKey, setPeriodKey, compare, setCompare } = useDashboard();
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label={t("period.label")}>
      {PERIOD_KEYS.map((key: PeriodKey) => (
        <button
          key={key}
          onClick={() => setPeriodKey(key)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            periodKey === key
              ? "bg-flame text-white"
              : "text-ink-soft hover:bg-flame-soft hover:text-ink"
          }`}
        >
          {t(`period.${key}`)}
        </button>
      ))}
      <label className="ml-2 flex cursor-pointer items-center gap-1.5 text-xs text-ink-soft">
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

export default function Shell() {
  const { t } = useTranslation();
  const { me, projects, orgId, setOrgId, logout } = useDashboard();
  const { projectId } = useParams();

  return (
    <div className="paper-grain min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-2.5">
          <NavLink to="/" className="flex items-center gap-2">
            <Flame />
            <span className="font-display text-lg font-bold tracking-tight">
              {t("app.name")}
            </span>
          </NavLink>

          {me && me.orgs.length > 1 && (
            <select
              aria-label={t("common.organization")}
              value={orgId ?? ""}
              onChange={(event) => setOrgId(event.target.value)}
              className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
            >
              {me.orgs.map((membership) => (
                <option key={membership.org_id} value={membership.org_id}>
                  {membership.org_id.slice(0, 8)}
                </option>
              ))}
            </select>
          )}

          <nav className="flex items-center gap-1 text-sm">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `rounded-md px-2.5 py-1 ${isActive ? "bg-flame-soft font-semibold text-flame" : "text-ink-soft hover:text-ink"}`
              }
            >
              {t("nav.home")}
            </NavLink>
            {projectId && (
              <>
                <NavLink
                  to={`/p/${projectId}/web`}
                  className={({ isActive }) =>
                    `rounded-md px-2.5 py-1 ${isActive ? "bg-flame-soft font-semibold text-flame" : "text-ink-soft hover:text-ink"}`
                  }
                >
                  {t("nav.web")}
                </NavLink>
                <NavLink
                  to={`/p/${projectId}/api`}
                  className={({ isActive }) =>
                    `rounded-md px-2.5 py-1 ${isActive ? "bg-flame-soft font-semibold text-flame" : "text-ink-soft hover:text-ink"}`
                  }
                >
                  {t("nav.api")}
                </NavLink>
              </>
            )}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {projectId && (
              <select
                aria-label={t("common.project")}
                value={projectId}
                onChange={(event) =>
                  window.location.assign(
                    window.location.pathname.replace(projectId, event.target.value),
                  )
                }
                className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            )}
            <LangToggle />
            <ThemeToggle />
            <button
              onClick={logout}
              className="rounded-md px-2 py-1 text-xs text-ink-soft hover:text-flame"
            >
              {t("nav.logout")}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
