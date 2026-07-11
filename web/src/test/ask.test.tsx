import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderApp } from "./render";
import { server } from "./server";

const openPalette = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.keyboard("{Control>}k{/Control}");
  return within(await screen.findByRole("dialog"));
};

describe("Ask Oriflux ⌘K palette", () => {
  it("opens with Ctrl+K from any authenticated view and answers with the executed query", async () => {
    server.use(
      http.post("/api/v1/ask", () =>
        HttpResponse.json({
          question: "visiteurs par pays",
          query: { metric: "visitors", dimensions: ["country"] },
          sql: "SELECT country …",
          results: [
            { country: "FR", value: 569 },
            { country: "DE", value: 214 },
          ],
          answer: "La France domine avec 569 visiteurs.",
        }),
      ),
    );
    const user = userEvent.setup();
    renderApp("/p/p1/web");
    await screen.findAllByText("Visiteurs");

    const palette = await openPalette(user);
    await user.type(palette.getByRole("textbox"), "visiteurs par pays");
    await user.click(palette.getByRole("button", { name: "Demander" }));

    expect(await palette.findByText("La France domine avec 569 visiteurs.")).toBeInTheDocument();
    // transparency: the typed query is always visible
    expect(palette.getByText("Requête exécutée")).toBeInTheDocument();
    expect(palette.getByText(/"metric": "visitors"/)).toBeInTheDocument();
    expect(palette.getByText(/SELECT country/)).toBeInTheDocument();
  });

  it("shows the dedicated budget-exhausted message on 429", async () => {
    server.use(
      http.post("/api/v1/ask", () => HttpResponse.json({ detail: "budget" }, { status: 429 })),
    );
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("heading", { name: "Portefeuille" });

    const palette = await openPalette(user);
    await user.type(palette.getByRole("textbox"), "combien de visiteurs ?");
    await user.click(palette.getByRole("button", { name: "Demander" }));
    expect(await palette.findByText("Budget IA mensuel épuisé.")).toBeInTheDocument();
  });

  it("shows the AI-disabled message on 503 and closes on Escape", async () => {
    server.use(
      http.post("/api/v1/ask", () => HttpResponse.json({ detail: "off" }, { status: 503 })),
    );
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("heading", { name: "Portefeuille" });

    const palette = await openPalette(user);
    await user.type(palette.getByRole("textbox"), "question");
    await user.click(palette.getByRole("button", { name: "Demander" }));
    expect(
      await palette.findByText("L'IA n'est pas configurée sur cette instance."),
    ).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
