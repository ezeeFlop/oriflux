import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { Annotation } from "../lib/api";
import { renderApp } from "./render";
import { server } from "./server";

describe("per-project live view", () => {
  it("renders project-scoped active pages and the fallback state", async () => {
    server.use(
      http.post("/api/v1/query", async ({ request }) => {
        const body = (await request.json()) as {
          dimensions?: string[];
          filters?: { dimension: string; value: unknown }[];
        };
        // the live view must scope its 30-min queries to the project
        expect(body.filters?.some((f) => f.dimension === "project_id" && f.value === "p1")).toBe(
          true,
        );
        const dimension = body.dimensions?.[0];
        return HttpResponse.json({
          metric: "visitors",
          results:
            dimension === "page"
              ? [{ value: 9, page: "/docs" }]
              : [{ value: 5, country: "FR" }],
          compare_results: null,
          sql: "SELECT 1",
        });
      }),
    );
    renderApp("/p/p1/live");
    expect(await screen.findByText("/docs")).toBeInTheDocument();
    // the WS stub never connects: the view reports the polling fallback
    expect(screen.getByText("repli 10 s")).toBeInTheDocument();
  });
});

describe("annotations view", () => {
  let annotations: Annotation[];

  beforeEach(() => {
    annotations = [];
    server.use(
      http.get("/api/v1/projects/:projectId/annotations", () => HttpResponse.json(annotations)),
      http.post("/api/v1/projects/:projectId/annotations", async ({ request }) => {
        const body = (await request.json()) as Pick<Annotation, "kind" | "text" | "happened_at">;
        const annotation = { id: `a-${annotations.length + 1}`, ...body };
        annotations = [...annotations, annotation];
        return HttpResponse.json(annotation, { status: 201 });
      }),
      http.delete("/api/v1/annotations/:annotationId", ({ params }) => {
        annotations = annotations.filter((a) => a.id !== params.annotationId);
        return new HttpResponse(null, { status: 204 });
      }),
    );
  });

  it("creates then deletes an annotation", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/annotations");
    await user.type(
      await screen.findByLabelText("Texte de l'annotation"),
      "v2.1 déployée",
    );
    await user.selectOptions(screen.getByLabelText("Type"), "release");
    await user.click(screen.getByRole("button", { name: "Annoter" }));
    expect(await screen.findByText("v2.1 déployée")).toBeInTheDocument();

    const row = screen.getByText("v2.1 déployée").closest("li") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Supprimer l'annotation" }));
    expect(await screen.findByText("Aucune annotation sur cette période.")).toBeInTheDocument();
  });
});
