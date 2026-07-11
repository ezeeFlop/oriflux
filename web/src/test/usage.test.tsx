import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderApp } from "./render";
import { server } from "./server";

const usage = (used: number, limit: number) =>
  http.get("/api/v1/orgs/:orgId/usage", () =>
    HttpResponse.json({
      plan_slug: "pro",
      plan_name: "Pro",
      monthly_events: limit,
      used,
      pct: Math.round((used / limit) * 1000) / 10,
    }),
  );

describe("plan & usage (issue #61)", () => {
  it("shows the plan, the gauge and the numbers in org settings", async () => {
    server.use(usage(250_000, 1_000_000));
    renderApp("/settings/org");
    expect(await screen.findByText("Plan & usage")).toBeInTheDocument();
    expect(await screen.findByText("Pro")).toBeInTheDocument();
    expect(screen.getByText(/250[  ]?000/)).toBeInTheDocument();
    expect(screen.getByText("25 %")).toBeInTheDocument();
    // under 80%: no warning banner
    expect(screen.queryByText(/envisagez un plan supérieur/)).not.toBeInTheDocument();
  });

  it("warns in the shell from 80% of quota", async () => {
    server.use(usage(920_000, 1_000_000));
    renderApp("/");
    expect(await screen.findByText(/Quota d'événements à 92 %/)).toBeInTheDocument();
  });

  it("shows the unlimited state for internal plans", async () => {
    renderApp("/settings/org");
    expect(
      await screen.findByText("Plan interne — sans limite d'événements."),
    ).toBeInTheDocument();
  });
});
