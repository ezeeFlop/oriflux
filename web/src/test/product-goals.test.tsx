import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { Goal } from "../lib/api";
import { renderApp } from "./render";
import { server } from "./server";

let goals: Goal[];

beforeEach(() => {
  goals = [];
  server.use(
    http.get("/api/v1/projects/:projectId/goals", () => HttpResponse.json(goals)),
    http.post("/api/v1/projects/:projectId/goals", async ({ request }) => {
      const body = (await request.json()) as Pick<Goal, "name" | "kind" | "target">;
      const goal: Goal = { id: `g-${goals.length + 1}`, conversions: 3, conversion_rate: 1.5, ...body };
      goals = [...goals, goal];
      return HttpResponse.json(goal, { status: 201 });
    }),
    http.delete("/api/v1/goals/:goalId", ({ params }) => {
      goals = goals.filter((g) => g.id !== params.goalId);
      return new HttpResponse(null, { status: 204 });
    }),
  );
});

describe("goals view (rehomed)", () => {
  it("creates and deletes a goal from its own sidebar entry", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/goals");
    expect(await screen.findByRole("heading", { level: 1, name: "Objectifs" })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Nom"), "Inscription");
    await user.type(screen.getByPlaceholderText("/pricing"), "/signup");
    await user.click(screen.getByRole("button", { name: "Ajouter" }));
    expect(await screen.findByText("Inscription")).toBeInTheDocument();

    const row = screen.getByText("Inscription").closest("tr") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Supprimer" }));
    expect(await screen.findByText(/Aucun objectif/)).toBeInTheDocument();
  });
});

describe("funnels & retention view (rehomed)", () => {
  it("renders the funnel with its session-scope privacy note", async () => {
    renderApp("/p/p1/product");
    expect(await screen.findByRole("heading", { name: "Funnels & rétention" })).toBeInTheDocument();
    expect(await screen.findByText(/limités à une session\/journée/)).toBeInTheDocument();
  });

  it("renders retention with its identified-only privacy note", async () => {
    renderApp("/p/p1/product");
    expect(
      await screen.findByText(/rétention anonyme inter-jours est impossible/),
    ).toBeInTheDocument();
  });
});
