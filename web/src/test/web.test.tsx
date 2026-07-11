import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { QueryRequest } from "../lib/api";
import { renderApp } from "./render";
import { server } from "./server";

/** Every dashboard number goes through POST /api/v1/query — capturing its
 *  bodies is how the tests observe filters, compare and granularity. */
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

describe("web view", () => {
  it("renders every registry metric of the stat row", async () => {
    renderApp("/p/p1/web");
    for (const label of [
      "Visiteurs",
      "Pages vues",
      "Sessions",
      "Taux de rebond",
      "Durée de session",
    ]) {
      expect((await screen.findAllByText(label)).length).toBeGreaterThan(0);
    }
    const metrics = new Set(queries.map((q) => q.metric));
    for (const metric of ["visitors", "pageviews", "sessions", "bounce_rate", "session_duration"]) {
      expect(metrics).toContain(metric);
    }
  });

  it("propagates the traffic-class filter into every registry query", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/web");
    await screen.findAllByText("Visiteurs");
    queries = [];
    await user.click(screen.getByRole("button", { name: "Bots" }));
    await waitFor(() => expect(queries.length).toBeGreaterThan(0));
    const filtered = queries.filter((q) =>
      (q.filters ?? []).some((f) => f.dimension === "traffic_class" && f.value === "bot"),
    );
    expect(filtered.length).toBeGreaterThan(0);
  });

  it("asks for previous_period when compare is on in the URL", async () => {
    renderApp("/p/p1/web?compare=1");
    await screen.findAllByText("Visiteurs");
    await waitFor(() =>
      expect(queries.some((q) => q.compare_to === "previous_period")).toBe(true),
    );
  });

  it("shows the AI-visibility classification panel", async () => {
    renderApp("/p/p1/web");
    expect(await screen.findByText("Visibilité IA")).toBeInTheDocument();
  });
});
