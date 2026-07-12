import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { QueryRequest } from "../lib/api";
import { currentLocation, renderApp } from "./render";
import { server } from "./server";

/** Every dashboard number goes through POST /api/v1/query — capturing its
 *  bodies is how the tests observe metrics, filters and compare. */
let queries: QueryRequest[];

beforeEach(() => {
  queries = [];
  server.use(
    http.post("/api/v1/query", async ({ request }) => {
      const body = (await request.json()) as QueryRequest;
      queries.push(body);
      return HttpResponse.json({
        metric: body.metric,
        results: [{ value: 42, bucket: "2026-07-10T00:00:00Z" }],
        compare_results: body.compare_to ? [{ value: 21 }] : null,
        sql: "SELECT 1",
      });
    }),
  );
});

describe("overview view", () => {
  it("is the project index — /p/:id lands on the overview, keeping the query string", async () => {
    renderApp("/p/p1?period=30d");
    await waitFor(() => expect(currentLocation()).toBe("/p/p1/overview?period=30d"));
    expect((await screen.findAllByText("Vue d'ensemble")).length).toBeGreaterThan(0);
  });

  it("renders the web + API + live KPI band through the registry", async () => {
    renderApp("/p/p1/overview");
    for (const label of ["Visiteurs", "Pages vues", "Sessions", "Requêtes API", "Erreurs 5xx", "Latence p95"]) {
      expect((await screen.findAllByText(label)).length).toBeGreaterThan(0);
    }
    const metrics = new Set(queries.map((q) => q.metric));
    for (const metric of [
      "visitors",
      "pageviews",
      "sessions",
      "api_requests",
      "api_error_rate_5xx",
      "api_latency_p95",
    ]) {
      expect(metrics).toContain(metric);
    }
  });

  it("always compares KPIs to the previous period, without the compare toggle", async () => {
    renderApp("/p/p1/overview");
    await screen.findAllByText("Visiteurs");
    await waitFor(() =>
      expect(queries.filter((q) => q.compare_to === "previous_period").length).toBeGreaterThan(0),
    );
    // 42 vs 21 → a +100 % delta must be visible on the cards
    expect((await screen.findAllByText(/▲ 100/)).length).toBeGreaterThan(0);
  });

  it("shows the combined web+API trend on the selected period", async () => {
    renderApp("/p/p1/overview");
    expect(await screen.findByText("Tendance web + API")).toBeInTheDocument();
    await waitFor(() => {
      const withGranularity = queries.filter((q) => q.granularity !== null && q.granularity !== undefined);
      const metrics = new Set(withGranularity.map((q) => q.metric));
      expect(metrics).toContain("pageviews");
      expect(metrics).toContain("api_requests");
    });
  });

  it("shows the project's recent alerts and annotations with links to their screens", async () => {
    server.use(
      http.get("/api/v1/orgs/:orgId/alert-events", () =>
        HttpResponse.json([
          {
            id: "ev-1",
            rule_id: "r1",
            rule_name: "5xx spike",
            project_id: "p1",
            metric: "api_error_rate_5xx",
            value: 7.5,
            fired_at: "2026-07-11T10:00:00Z",
            resolved_at: null,
          },
          {
            id: "ev-2",
            rule_id: "r2",
            rule_name: "other project rule",
            project_id: "p2",
            metric: "visitors",
            value: 3,
            fired_at: "2026-07-11T09:00:00Z",
            resolved_at: null,
          },
        ]),
      ),
      http.get("/api/v1/projects/:projectId/annotations", () =>
        HttpResponse.json([
          { id: "a1", kind: "release", text: "v2 déployée", happened_at: "2026-07-10T08:00:00Z" },
        ]),
      ),
    );
    renderApp("/p/p1/overview");
    expect(await screen.findByText("5xx spike")).toBeInTheDocument();
    // events from other projects stay off this project's overview
    expect(screen.queryByText("other project rule")).not.toBeInTheDocument();
    expect(await screen.findByText("v2 déployée")).toBeInTheDocument();
  });

  it("offers shortcuts into the project's sections", async () => {
    renderApp("/p/p1/overview");
    await screen.findAllByText("Visiteurs");
    for (const name of ["Web", "API", "Live", "Alertes"]) {
      const links = screen
        .getAllByRole("link", { name })
        .filter((link) => link.getAttribute("href")?.startsWith("/p/p1/"));
      expect(links.length).toBeGreaterThan(0);
    }
  });

  it("explains the instrumentation state instead of mute zeros when nothing was emitted", async () => {
    server.use(
      http.post("/api/v1/query", async ({ request }) => {
        const body = (await request.json()) as QueryRequest;
        return HttpResponse.json({
          metric: body.metric,
          results: [{ value: 0, bucket: "2026-07-10T00:00:00Z" }],
          compare_results: body.compare_to ? [{ value: 0 }] : null,
          sql: "SELECT 1",
        });
      }),
    );
    renderApp("/p/p1/overview");
    expect(
      await screen.findByText("Ce projet n'a encore émis aucun événement sur la période."),
    ).toBeInTheDocument();
    const settingsLink = screen.getByRole("link", { name: "Ouvrir les réglages du projet" });
    expect(settingsLink.getAttribute("href")).toBe("/p/p1/settings");
  });
});
