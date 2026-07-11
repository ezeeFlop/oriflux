import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { renderApp } from "./render";
import { server } from "./server";

beforeEach(() => {
  server.use(
    http.get("/api/v1/orgs/:orgId/alert-events", () =>
      HttpResponse.json([
        {
          id: "ev-1",
          rule_id: "r-1",
          rule_name: "5xx AudiGEO",
          project_id: "p1",
          metric: "api_error_rate_5xx",
          value: 7.2,
          fired_at: "2026-07-11T08:00:00Z",
          resolved_at: null,
        },
      ]),
    ),
    http.get("/api/v1/orgs/:orgId/insights", () =>
      HttpResponse.json([
        {
          id: "in-1",
          project_name: "AudiGEO",
          day: "2026-07-11",
          kind: "trend",
          metric: "visitors",
          numbers: { current: 120, previous: 80, delta_pct: 50, window: "day" },
          query: {},
          text: "Le trafic FR progresse de 50 % sur un jour.",
        },
      ]),
    ),
    http.get("/api/v1/orgs/:orgId/anomalies", () =>
      HttpResponse.json([
        {
          id: "an-1",
          project_id: "p2",
          project_name: "NeoRAG",
          metric: "api_requests",
          direction: "drop",
          expected: 900,
          observed: 300,
          deviation_pct: -66,
          window_start: "2026-07-11T07:00:00Z",
          explanation: "La chute vient du consommateur cliphaven (‑80 %).",
        },
      ]),
    ),
  );
});

describe("portfolio home", () => {
  it("shows recent alerts with their state, linked to the project", async () => {
    renderApp("/?period=30d");
    expect(await screen.findByText("Alertes récentes")).toBeInTheDocument();
    expect(await screen.findByText("5xx AudiGEO")).toBeInTheDocument();
    expect(screen.getByText("En cours", { exact: false })).toBeInTheDocument();
    const link = screen.getByText("5xx AudiGEO").closest("a");
    expect(link).toHaveAttribute("href", "/p/p1/alerts?period=30d");
  });

  it("shows the insights feed with its explanation text", async () => {
    renderApp("/");
    expect(
      await screen.findByText("Le trafic FR progresse de 50 % sur un jour."),
    ).toBeInTheDocument();
  });

  it("shows anomalies with their grounded diagnosis", async () => {
    renderApp("/");
    expect(
      await screen.findByText("La chute vient du consommateur cliphaven (‑80 %)."),
    ).toBeInTheDocument();
  });

  it("renders the live globe section", async () => {
    renderApp("/");
    expect(await screen.findByText("Monde en direct")).toBeInTheDocument();
  });
});
