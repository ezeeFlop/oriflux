import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { QueryRequest } from "../lib/api";
import { currentLocation, renderApp } from "./render";
import { server } from "./server";

let queries: QueryRequest[];

beforeEach(() => {
  queries = [];
  server.use(
    http.post("/api/v1/query", async ({ request }) => {
      const body = (await request.json()) as QueryRequest;
      queries.push(body);
      const dimension = body.dimensions?.[0];
      const results =
        dimension === "country"
          ? [
              { value: 120, country: "DE" },
              { value: 80, country: "FR" },
            ]
          : dimension
            ? [{ value: 10, [dimension]: "x" }]
            : [{ value: 42 }];
      return HttpResponse.json({ metric: body.metric, results, compare_results: null, sql: "SELECT 1" });
    }),
  );
});

const apiGeoPanel = async () => {
  const heading = await screen.findByRole("heading", { name: "Géographie des appelants" });
  return within(heading.closest("section") as HTMLElement);
};

describe("API caller geography (issue #51)", () => {
  it("renders the choropleth colored by request volume", async () => {
    renderApp("/p/p1/api");
    const panel = await apiGeoPanel();
    expect(await panel.findByRole("button", { name: /Germany — 120/ })).toBeInTheDocument();
  });

  it("switches the map metric to p95 latency", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/api");
    const panel = await apiGeoPanel();
    await panel.findByRole("button", { name: /Germany — 120/ });
    queries = [];
    await user.click(panel.getByRole("button", { name: "Latence p95" }));
    await waitFor(() =>
      expect(
        queries.some(
          (q) => q.metric === "api_latency_p95" && q.dimensions?.[0] === "country",
        ),
      ).toBe(true),
    );
  });

  it("clicking a country cross-filters the whole API view via the URL", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/api");
    const panel = await apiGeoPanel();
    queries = [];
    await user.click(await panel.findByRole("button", { name: /Germany — 120/ }));
    expect(currentLocation()).toContain("country=DE");
    await waitFor(() => {
      const filtered = queries.filter(
        (q) =>
          q.metric === "api_requests" &&
          q.dimensions?.[0] === "endpoint" &&
          (q.filters ?? []).some((f) => f.dimension === "country" && f.value === "DE"),
      );
      expect(filtered.length).toBeGreaterThan(0);
    });
  });
});
