/** Default MSW handlers replaying the /api/v1 contract (the same contract
 *  the backend covers server-side). Tests override per-case as needed. */

import { http, HttpResponse } from "msw";

export const ME = {
  id: "user-1",
  email: "christophe@sponge-theory.io",
  name: "Christophe",
  orgs: [{ org_id: "org-1", role: "owner" }],
};

export const PROJECTS = [
  { id: "p1", slug: "audigeo", name: "AudiGEO" },
  { id: "p2", slug: "neorag", name: "NeoRAG" },
];

const queryResponse = (metric: string) => ({
  metric,
  results: [
    { value: 42, bucket: "2026-07-10T00:00:00Z" },
    { value: 57, bucket: "2026-07-11T00:00:00Z" },
  ],
  compare_results: null,
  sql: "SELECT 1",
});

export const handlers = [
  http.get("/api/v1/me", () => HttpResponse.json(ME)),
  http.get("/api/v1/orgs/:orgId/projects", () => HttpResponse.json(PROJECTS)),
  http.post("/api/v1/query", async ({ request }) => {
    const body = (await request.json()) as { metric: string };
    return HttpResponse.json(queryResponse(body.metric));
  }),
  http.post("/api/v1/funnel", () =>
    HttpResponse.json({
      scope: "session",
      steps: [{ step: 1, target: "/", entered: 10 }],
      conversion_rate: 1,
    }),
  ),
  http.post("/api/v1/retention", () =>
    HttpResponse.json({
      granularity: "week",
      activation_event: "signup",
      cohorts: [],
    }),
  ),
  http.post("/api/v1/ask", () =>
    HttpResponse.json({
      question: "q",
      query: {},
      sql: "SELECT 1",
      results: [],
      answer: "42",
    }),
  ),
  http.get("/api/v1/projects/:projectId/sources", () => HttpResponse.json([])),
  http.get("/api/v1/orgs/:orgId/keys", () => HttpResponse.json([])),
  http.get("/api/v1/projects/:projectId/goals", () => HttpResponse.json([])),
  http.get("/api/v1/projects/:projectId/annotations", () => HttpResponse.json([])),
  http.get("/api/v1/projects/:projectId/infra", () =>
    HttpResponse.json({ available: false }),
  ),
  http.get("/api/v1/orgs/:orgId/anomalies", () => HttpResponse.json([])),
  http.get("/api/v1/orgs/:orgId/insights", () => HttpResponse.json([])),
];
