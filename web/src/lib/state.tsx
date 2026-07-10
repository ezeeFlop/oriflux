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
import { auth, fetchMe, listProjects, type Me, type Project, type QueryFilter } from "./api";
import { granularityFor, periodFor, type PeriodKey } from "./periods";

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
  /** filters shared by every web widget: project + optional traffic class */
  webFilters: (projectId: string) => QueryFilter[];
  period: { start: string; end: string };
  granularity: "hour" | "day" | "week" | "month";
  logout: () => void;
}

const DashboardContext = createContext<Dashboard | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [orgId, setOrgIdState] = useState<string | null>(auth.orgId);
  const [periodKey, setPeriodKey] = useState<PeriodKey>("7d");
  const [compare, setCompare] = useState(false);
  const [trafficClass, setTrafficClass] = useState<TrafficClass>("all");

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
      webFilters: (projectId: string) => {
        const filters: QueryFilter[] = [{ dimension: "project_id", op: "eq", value: projectId }];
        if (trafficClass !== "all") {
          filters.push({ dimension: "traffic_class", op: "eq", value: trafficClass });
        }
        return filters;
      },
      period,
      granularity: granularityFor(periodKey),
      logout,
    };
  }, [me, loadingSession, effectiveOrg, setOrgId, projects, periodKey, compare, trafficClass, logout]);

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard(): Dashboard {
  const context = useContext(DashboardContext);
  if (!context) throw new Error("useDashboard outside provider");
  return context;
}
