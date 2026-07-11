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
              { value: 569, country: "FR" },
              { value: 214, country: "DE" },
            ]
          : dimension === "region"
            ? [{ value: 300, region: "Île-de-France" }]
            : [{ value: 42, bucket: "2026-07-10T00:00:00Z" }];
      return HttpResponse.json({ metric: body.metric, results, compare_results: null, sql: "SELECT 1" });
    }),
  );
});

const geoPanel = async () => {
  const heading = await screen.findByRole("heading", { name: "Géographie" });
  return within(heading.closest("section") as HTMLElement);
};

describe("geo choropleth (issue #50)", () => {
  it("renders the embedded basemap with every country shape", async () => {
    renderApp("/p/p1/web");
    const panel = await geoPanel();
    const france = await panel.findByRole("button", { name: /France — 569/ });
    expect(france).toBeInTheDocument();
    // the basemap ships >150 countries even when only two have data
    expect(panel.getAllByRole("button", { name: /.+/ }).length).toBeGreaterThan(150);
  });

  it("clicking a country writes the cross-filter to the URL and to every query", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/web");
    const panel = await geoPanel();
    queries = [];
    await user.click(await panel.findByRole("button", { name: /France — 569/ }));
    expect(currentLocation()).toContain("country=FR");
    await waitFor(() => {
      const filtered = queries.filter((q) =>
        (q.filters ?? []).some((f) => f.dimension === "country" && f.value === "FR"),
      );
      expect(filtered.length).toBeGreaterThan(0);
    });
  });

  it("drills the table to regions when a country is selected in the URL", async () => {
    renderApp("/p/p1/web?country=FR");
    const panel = await geoPanel();
    expect(await panel.findByText("Île-de-France")).toBeInTheDocument();
    await waitFor(() =>
      expect(queries.some((q) => q.dimensions?.[0] === "region")).toBe(true),
    );
  });

  it("the world-total breadcrumb clears the geo filter", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/web?country=FR&region=Bretagne");
    const panel = await geoPanel();
    await user.click(panel.getByRole("button", { name: "Monde entier" }));
    expect(currentLocation()).not.toContain("country=");
    expect(currentLocation()).not.toContain("region=");
  });
});
