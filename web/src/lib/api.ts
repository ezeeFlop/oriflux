/** API client — every analytics number flows through POST /api/v1/query
 *  (the typed registry contract). No bespoke query paths, ever. */

export interface Period {
  start: string;
  end: string;
}

export interface QueryFilter {
  dimension: string;
  op: "eq" | "neq" | "in";
  value: string | string[];
}

export interface QueryRequest {
  metric: string;
  dimensions?: string[];
  filters?: QueryFilter[];
  granularity?: "hour" | "day" | "week" | "month" | null;
  period: Period;
  compare_to?: "previous_period" | "previous_year" | null;
}

export interface QueryRow {
  value: number | null;
  bucket?: string;
  [dimension: string]: unknown;
}

export interface QueryResponse {
  metric: string;
  results: QueryRow[];
  compare_results: QueryRow[] | null;
  sql: string;
}

const TOKEN_KEY = "oriflux.token";
const ORG_KEY = "oriflux.org";

export const auth = {
  get token(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  set token(value: string | null) {
    if (value === null) localStorage.removeItem(TOKEN_KEY);
    else localStorage.setItem(TOKEN_KEY, value);
  },
  get orgId(): string | null {
    return localStorage.getItem(ORG_KEY);
  },
  set orgId(value: string | null) {
    if (value === null) localStorage.removeItem(ORG_KEY);
    else localStorage.setItem(ORG_KEY, value);
  },
};

export class ApiError extends Error {
  constructor(
    public status: number,
    detail: string,
  ) {
    super(detail);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) ?? {}),
  };
  if (auth.token) headers["Authorization"] = `Bearer ${auth.token}`;
  if (auth.orgId) headers["X-Oriflux-Org"] = auth.orgId;

  const response = await fetch(path, { ...init, headers });
  if (response.status === 401) {
    auth.token = null;
    window.location.assign("/login");
    throw new ApiError(401, "session expired");
  }
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function runQuery(request: QueryRequest): Promise<QueryResponse> {
  return apiFetch<QueryResponse>("/api/v1/query", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export interface Project {
  id: string;
  slug: string;
  name: string;
}

export function listProjects(orgId: string): Promise<Project[]> {
  return apiFetch<Project[]>(`/api/v1/orgs/${orgId}/projects`);
}

export function createProject(
  orgId: string,
  project: { slug: string; name: string },
): Promise<Project> {
  return apiFetch<Project>(`/api/v1/orgs/${orgId}/projects`, {
    method: "POST",
    body: JSON.stringify(project),
  });
}

export type SourceType = "web" | "app" | "api";

export interface Source {
  id: string;
  project_id: string;
  type: SourceType;
  name: string;
}

export function listSources(projectId: string): Promise<Source[]> {
  return apiFetch<Source[]>(`/api/v1/projects/${projectId}/sources`);
}

export function createSource(
  projectId: string,
  source: { type: SourceType; name: string },
): Promise<Source> {
  return apiFetch<Source>(`/api/v1/projects/${projectId}/sources`, {
    method: "POST",
    body: JSON.stringify(source),
  });
}

/** Plaintext appears exactly once, in this issuance response. */
export interface IssuedKey {
  id: string;
  key: string;
  key_prefix: string;
  scope: "ingest" | "read";
  name: string;
}

export interface ApiKeyRow {
  id: string;
  scope: "ingest" | "read";
  name: string;
  key_prefix: string;
  source_id: string | null;
  revoked: boolean;
  created_at: string;
}

export function issueIngestKey(sourceId: string, name: string): Promise<IssuedKey> {
  return apiFetch<IssuedKey>(`/api/v1/sources/${sourceId}/keys`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function issueReadKey(orgId: string, name: string): Promise<IssuedKey> {
  return apiFetch<IssuedKey>(`/api/v1/orgs/${orgId}/keys`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function listKeys(orgId: string): Promise<ApiKeyRow[]> {
  return apiFetch<ApiKeyRow[]>(`/api/v1/orgs/${orgId}/keys`);
}

export function revokeKey(keyId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/keys/${keyId}`, { method: "DELETE" });
}

export type Role = "owner" | "admin" | "viewer";

export interface Member {
  user_id: string;
  email: string;
  name: string;
  role: Role;
}

export function listMembers(orgId: string): Promise<Member[]> {
  return apiFetch<Member[]>(`/api/v1/orgs/${orgId}/members`);
}

export function addMember(orgId: string, member: { email: string; role: Role }): Promise<void> {
  return apiFetch<void>(`/api/v1/orgs/${orgId}/members`, {
    method: "POST",
    body: JSON.stringify(member),
  });
}

export interface DigestPref {
  cadence: "weekly" | "monthly";
  language: "fr" | "en" | "es";
}

/** 404 means "not subscribed" — surfaced as null, not an error. */
export async function getDigestPref(orgId: string): Promise<DigestPref | null> {
  try {
    return await apiFetch<DigestPref>(`/api/v1/orgs/${orgId}/digest`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function setDigestPref(orgId: string, pref: DigestPref): Promise<DigestPref> {
  return apiFetch<DigestPref>(`/api/v1/orgs/${orgId}/digest`, {
    method: "PUT",
    body: JSON.stringify(pref),
  });
}

export function unsubscribeDigest(orgId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/orgs/${orgId}/digest`, { method: "DELETE" });
}

/** The share URL is copyable at mint time only (the server keeps a hash). */
export interface MintedShare {
  id: string;
  token: string;
  public_path: string;
}

export interface ShareRow {
  id: string;
  created_at: string;
  revoked: boolean;
}

export function mintShare(projectId: string): Promise<MintedShare> {
  return apiFetch<MintedShare>(`/api/v1/projects/${projectId}/share`, { method: "POST" });
}

export function listShares(projectId: string): Promise<ShareRow[]> {
  return apiFetch<ShareRow[]>(`/api/v1/projects/${projectId}/shares`);
}

export function revokeShare(shareId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/share/${shareId}`, { method: "DELETE" });
}

export interface Goal {
  id: string;
  name: string;
  kind: "event" | "page";
  target: string;
  conversions: number | null;
  conversion_rate: number | null;
}

export function listGoals(
  projectId: string,
  period?: { start: string; end: string },
): Promise<Goal[]> {
  const query = period
    ? `?start=${encodeURIComponent(period.start)}&end=${encodeURIComponent(period.end)}`
    : "";
  return apiFetch<Goal[]>(`/api/v1/projects/${projectId}/goals${query}`);
}

export function createGoal(
  projectId: string,
  goal: { name: string; kind: "event" | "page"; target: string },
): Promise<Goal> {
  return apiFetch<Goal>(`/api/v1/projects/${projectId}/goals`, {
    method: "POST",
    body: JSON.stringify(goal),
  });
}

export function deleteGoal(goalId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/goals/${goalId}`, { method: "DELETE" });
}

export interface FunnelStep {
  kind: "event" | "page";
  target: string;
}

export interface FunnelResult {
  scope: "session" | "identified";
  steps: { step: number; target: string; entered: number }[];
  conversion_rate: number;
}

export function runFunnel(request: {
  steps: FunnelStep[];
  scope: "session" | "identified";
  project_id: string;
  period: { start: string; end: string };
}): Promise<FunnelResult> {
  return apiFetch<FunnelResult>("/api/v1/funnel", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export interface RetentionResult {
  granularity: "week" | "month";
  activation_event: string;
  cohorts: { cohort_start: string; offset: number; users: number }[];
}

export function runRetention(request: {
  activation_event: string;
  granularity: "week" | "month";
  project_id: string;
  period: { start: string; end: string };
}): Promise<RetentionResult> {
  return apiFetch<RetentionResult>("/api/v1/retention", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export interface Annotation {
  id: string;
  kind: "release" | "campaign" | "incident" | "note";
  text: string;
  happened_at: string;
}

export function listAnnotations(
  projectId: string,
  period: { start: string; end: string },
): Promise<Annotation[]> {
  return apiFetch<Annotation[]>(
    `/api/v1/projects/${projectId}/annotations?start=${encodeURIComponent(period.start)}&end=${encodeURIComponent(period.end)}`,
  );
}

export interface Anomaly {
  id: string;
  project_id: string;
  project_name: string;
  metric: string;
  direction: "drop" | "spike";
  expected: number;
  observed: number;
  deviation_pct: number;
  window_start: string;
  explanation?: string;
}

export function listAnomalies(orgId: string): Promise<Anomaly[]> {
  return apiFetch<Anomaly[]>(`/api/v1/orgs/${orgId}/anomalies`);
}

export interface InfraSnapshot {
  available: boolean;
  service?: string;
  cpu_percent?: number;
  memory_mb?: number;
  containers?: number;
}

export function fetchInfra(projectId: string): Promise<InfraSnapshot> {
  return apiFetch<InfraSnapshot>(`/api/v1/projects/${projectId}/infra`);
}

export interface AskResult {
  question: string;
  query: Record<string, unknown>;
  sql: string;
  results: QueryRow[];
  answer: string;
}

export function askOriflux(question: string, projectId?: string): Promise<AskResult> {
  return apiFetch<AskResult>("/api/v1/ask", {
    method: "POST",
    body: JSON.stringify({ question, project_id: projectId ?? null }),
  });
}

export interface Insight {
  id: string;
  project_name: string;
  day: string;
  kind: string;
  metric: string;
  numbers: { current: number; previous: number; delta_pct: number; window: string };
  query: Record<string, unknown>;
  text: string;
}

export function listInsights(orgId: string): Promise<Insight[]> {
  return apiFetch<Insight[]>(`/api/v1/orgs/${orgId}/insights`);
}

export interface AlertEvent {
  id: string;
  rule_id: string;
  rule_name: string;
  project_id: string | null;
  metric: string;
  value: number;
  fired_at: string;
  resolved_at: string | null;
}

export function listAlertEvents(orgId: string): Promise<AlertEvent[]> {
  return apiFetch<AlertEvent[]>(`/api/v1/orgs/${orgId}/alert-events`);
}

export interface Me {
  id: string;
  email: string;
  name: string;
  orgs: { org_id: string; role: string }[];
}

export function fetchMe(): Promise<Me> {
  return apiFetch<Me>("/api/v1/me");
}

export function loginWithGoogle(idToken: string): Promise<{ access_token: string }> {
  return apiFetch<{ access_token: string }>("/api/v1/auth/google", {
    method: "POST",
    body: JSON.stringify({ id_token: idToken }),
  });
}
