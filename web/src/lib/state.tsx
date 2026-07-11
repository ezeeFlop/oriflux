/** Dashboard-wide state: session, org, projects, period + compare, traffic
 *  class. One context so the period picker affects every widget consistently. */

import { useQuery } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useSearchParams } from "react-router-dom";
import { auth, fetchMe, listProjects, type Me, type Project, type QueryFilter } from "./api";
import { granularityFor, periodFor, PERIOD_KEYS, type PeriodKey } from "./periods";

export type TrafficClass = "all" | "human" | "bot" | "ai_agent";

interface Dashboard {
  me: Me | null;
  loadingSession: boolean;
  orgId: string | null;
  setOrgId: (id: string) => void;
  projects: Project[];
  periodKey: PeriodKey;
  setPeriodKey: (key: PeriodKey) => void;
  compare: boolean;
  setCompare: (on: boolean) => void;
  trafficClass: TrafficClass;
  setTrafficClass: (klass: TrafficClass) => void;
  /** geo cross-filter (issue #50) — URL-backed like period/compare */
  geo: { country: string | null; region: string | null };
  setGeo: (country: string | null, region: string | null) => void;
  /** filters shared by every web widget: project + traffic class + geo */
  webFilters: (projectId: string, options?: { ignoreGeo?: boolean }) => QueryFilter[];
  period: { start: string; end: string };
  granularity: "hour" | "day" | "week" | "month";
  logout: () => void;
}

const DashboardContext = createContext<Dashboard | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [orgId, setOrgIdState] = useState<string | null>(auth.orgId);
  const [trafficClass, setTrafficClass] = useState<TrafficClass>("all");

  // Period + compare live in the URL so any dashboard state is shareable
  // and survives navigation (issue #44).
  const [searchParams, setSearchParams] = useSearchParams();
  const rawPeriod = searchParams.get("period") as PeriodKey | null;
  const periodKey: PeriodKey =
    rawPeriod !== null && PERIOD_KEYS.includes(rawPeriod) ? rawPeriod : "7d";
  const compare = searchParams.get("compare") === "1";

  const setParam = useCallback(
    (name: string, value: string | null) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (value === null) next.delete(name);
          else next.set(name, value);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setPeriodKey = useCallback((key: PeriodKey) => setParam("period", key), [setParam]);
  const setCompare = useCallback((on: boolean) => setParam("compare", on ? "1" : null), [setParam]);

  const geoCountry = searchParams.get("country");
  const geoRegion = searchParams.get("region");
  const setGeo = useCallback(
    (country: string | null, region: string | null) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (country === null) next.delete("country");
          else next.set("country", country);
          if (region === null) next.delete("region");
          else next.set("region", region);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const { data: me = null, isLoading: loadingSession } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: auth.token !== null,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const effectiveOrg = orgId ?? me?.orgs[0]?.org_id ?? null;
  if (effectiveOrg && auth.orgId !== effectiveOrg) auth.orgId = effectiveOrg;

  const { data: projects = [] } = useQuery({
    queryKey: ["projects", effectiveOrg],
    queryFn: () => listProjects(effectiveOrg as string),
    enabled: effectiveOrg !== null && auth.token !== null,
    staleTime: 60 * 1000,
  });

  const setOrgId = useCallback((id: string) => {
    auth.orgId = id;
    setOrgIdState(id);
  }, []);

  const logout = useCallback(() => {
    auth.token = null;
    auth.orgId = null;
    window.location.assign("/login");
  }, []);

  const value = useMemo<Dashboard>(() => {
    const period = periodFor(periodKey);
    return {
      me,
      loadingSession,
      orgId: effectiveOrg,
      setOrgId,
      projects,
      periodKey,
      setPeriodKey,
      compare,
      setCompare,
      trafficClass,
      setTrafficClass,
      geo: { country: geoCountry, region: geoRegion },
      setGeo,
      webFilters: (projectId: string, options?: { ignoreGeo?: boolean }) => {
        const filters: QueryFilter[] = [{ dimension: "project_id", op: "eq", value: projectId }];
        if (trafficClass !== "all") {
          filters.push({ dimension: "traffic_class", op: "eq", value: trafficClass });
        }
        if (!options?.ignoreGeo) {
          if (geoCountry) filters.push({ dimension: "country", op: "eq", value: geoCountry });
          if (geoRegion) filters.push({ dimension: "region", op: "eq", value: geoRegion });
        }
        return filters;
      },
      period,
      granularity: granularityFor(periodKey),
      logout,
    };
  }, [me, loadingSession, effectiveOrg, setOrgId, projects, periodKey, setPeriodKey, compare, setCompare, trafficClass, geoCountry, geoRegion, setGeo, logout]);

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard(): Dashboard {
  const context = useContext(DashboardContext);
  if (!context) throw new Error("useDashboard outside provider");
  return context;
}
