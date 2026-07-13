import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import * as redirect from "../lib/redirect";
import { renderApp } from "./render";
import { server } from "./server";

const plan = (over: Record<string, unknown>) => ({
  slug: "x",
  name: "X",
  monthly_events: null,
  subscribable: false,
  annual_subscribable: false,
  amount_cents: null,
  amount_cents_annual: null,
  currency: null,
  ...over,
});

const ENABLED = {
  enabled: true,
  plan_slug: "free",
  has_customer: true,
  plans: [
    plan({ slug: "free", name: "Free", monthly_events: 100000 }),
    plan({
      slug: "pro",
      name: "Pro",
      monthly_events: 1000000,
      subscribable: true,
      annual_subscribable: true,
      amount_cents: 1900,
      amount_cents_annual: 19000,
      currency: "eur",
    }),
  ],
};

describe("billing section (issue #63)", () => {
  it("stays invisible on a keyless instance", async () => {
    renderApp("/settings/org");
    expect(await screen.findByText("Plan & usage")).toBeInTheDocument();
    expect(screen.queryByText("Abonnement")).not.toBeInTheDocument();
  });

  it("offers the subscribable upgrades and redirects to checkout", async () => {
    server.use(
      http.get("/api/v1/orgs/:orgId/billing", () => HttpResponse.json(ENABLED)),
      http.post("/api/v1/orgs/:orgId/billing/checkout", () =>
        HttpResponse.json({ url: "https://checkout.stripe.test/pro" }),
      ),
    );
    const assign = vi.spyOn(redirect, "redirectTo").mockImplementation(() => {});
    const user = userEvent.setup();
    renderApp("/settings/org");
    await user.click(await screen.findByRole("button", { name: "Passer en Pro" }));
    expect(assign).toHaveBeenCalledWith("https://checkout.stripe.test/pro");
  });

  it("shows the live Stripe amount and bills annually when the toggle is on", async () => {
    const bodies: Array<{ interval?: string }> = [];
    server.use(
      http.get("/api/v1/orgs/:orgId/billing", () => HttpResponse.json(ENABLED)),
      http.post("/api/v1/orgs/:orgId/billing/checkout", async ({ request }) => {
        bodies.push((await request.json()) as { interval?: string });
        return HttpResponse.json({ url: "https://checkout.stripe.test/pro" });
      }),
    );
    vi.spyOn(redirect, "redirectTo").mockImplementation(() => {});
    const user = userEvent.setup();
    renderApp("/settings/org");
    // monthly amount from Stripe (19,00 €), not a hardcoded string
    expect(await screen.findByText(/19/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Annuel" }));
    await user.click(screen.getByRole("button", { name: "Passer en Pro" }));
    expect(bodies.at(-1)?.interval).toBe("year");
  });

  it("opens the customer portal for an existing subscriber", async () => {
    server.use(
      http.get("/api/v1/orgs/:orgId/billing", () => HttpResponse.json(ENABLED)),
      http.post("/api/v1/orgs/:orgId/billing/portal", () =>
        HttpResponse.json({ url: "https://portal.stripe.test/cus_1" }),
      ),
    );
    const assign = vi.spyOn(redirect, "redirectTo").mockImplementation(() => {});
    const user = userEvent.setup();
    renderApp("/settings/org");
    await user.click(
      await screen.findByRole("button", { name: "Gérer l'abonnement (factures, annulation)" }),
    );
    expect(assign).toHaveBeenCalledWith("https://portal.stripe.test/cus_1");
  });
});
