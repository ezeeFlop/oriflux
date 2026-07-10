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
