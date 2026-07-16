import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { ApiKeyRow, Project, Source } from "../lib/api";
import { PROJECTS } from "./handlers";
import { renderApp } from "./render";
import { server } from "./server";

/** Stateful fake of the admin surface: the same contract the backend tests
 *  cover server-side, so the UI can be exercised end-to-end over HTTP. */
let projects: Project[];
let sources: Source[];
let keys: ApiKeyRow[];

beforeEach(() => {
  projects = [...PROJECTS];
  sources = [];
  keys = [];
  server.use(
    http.get("/api/v1/orgs/:orgId/projects", () => HttpResponse.json(projects)),
    http.post("/api/v1/orgs/:orgId/projects", async ({ request }) => {
      const body = (await request.json()) as { slug: string; name: string };
      const project = { id: `p-${projects.length + 1}`, ...body };
      projects = [...projects, project];
      return HttpResponse.json(project, { status: 201 });
    }),
    http.get("/api/v1/projects/:projectId/sources", ({ params }) =>
      HttpResponse.json(sources.filter((s) => s.project_id === params.projectId)),
    ),
    http.post("/api/v1/projects/:projectId/sources", async ({ params, request }) => {
      const body = (await request.json()) as { type: Source["type"]; name: string };
      const source = {
        id: `s-${sources.length + 1}`,
        project_id: String(params.projectId),
        ...body,
      };
      sources = [...sources, source];
      return HttpResponse.json(source, { status: 201 });
    }),
    http.post("/api/v1/sources/:sourceId/keys", () => {
      const row: ApiKeyRow = {
        id: `k-${keys.length + 1}`,
        scope: "ingest",
        name: "site",
        key_prefix: "ofx_ing_abc",
        source_id: "s-1",
        revoked: false,
        created_at: "2026-07-11T00:00:00Z",
      };
      keys = [...keys, row];
      return HttpResponse.json(
        { id: row.id, key: "ofx_ing_PLAINTEXT_ONCE", key_prefix: row.key_prefix, scope: "ingest", name: row.name },
        { status: 201 },
      );
    }),
    http.post("/api/v1/orgs/:orgId/keys", () => {
      const row: ApiKeyRow = {
        id: `k-${keys.length + 1}`,
        scope: "read",
        name: "mcp",
        key_prefix: "ofx_read_xyz",
        source_id: null,
        revoked: false,
        created_at: "2026-07-11T00:00:00Z",
      };
      keys = [...keys, row];
      return HttpResponse.json(
        { id: row.id, key: "ofx_read_PLAINTEXT_ONCE", key_prefix: row.key_prefix, scope: "read", name: row.name },
        { status: 201 },
      );
    }),
    http.get("/api/v1/orgs/:orgId/keys", () => HttpResponse.json(keys)),
    http.delete("/api/v1/keys/:keyId", ({ params }) => {
      keys = keys.map((k) => (k.id === params.keyId ? { ...k, revoked: true } : k));
      return new HttpResponse(null, { status: 204 });
    }),
  );
});

describe("org settings — the zero-terminal path", () => {
  it("creates a project from the UI and shows it in list and sidebar", async () => {
    const user = userEvent.setup();
    renderApp("/settings/org");
    await user.type(await screen.findByLabelText("Nom du projet"), "ClipHaven");
    await user.type(screen.getByLabelText("slug"), "cliphaven");
    await user.click(screen.getByRole("button", { name: "Créer le projet" }));
    const main = within(await screen.findByRole("main"));
    expect((await main.findAllByText("ClipHaven")).length).toBeGreaterThan(0);
    const aside = within(screen.getByRole("complementary"));
    expect(await aside.findByRole("link", { name: "ClipHaven" })).toBeInTheDocument();
  });

  it("creates a source inside a project", async () => {
    const user = userEvent.setup();
    renderApp("/settings/org");
    await user.click(await screen.findByRole("button", { name: /AudiGEO/ }));
    await user.type(await screen.findByLabelText("Nom de la source"), "audigeo.ai website");
    await user.selectOptions(screen.getByLabelText("Type de source"), "web");
    await user.click(screen.getByRole("button", { name: "Ajouter la source" }));
    expect(await screen.findByText("audigeo.ai website")).toBeInTheDocument();
  });

  it("issues an ingest key: plaintext + snippet shown once, then gone", async () => {
    const user = userEvent.setup();
    renderApp("/settings/org");
    await user.click(await screen.findByRole("button", { name: /AudiGEO/ }));
    await user.type(await screen.findByLabelText("Nom de la source"), "site");
    await user.click(screen.getByRole("button", { name: "Ajouter la source" }));
    await user.click(await screen.findByRole("button", { name: "Émettre une clé d'ingestion" }));

    const modal = within(await screen.findByRole("dialog"));
    expect(modal.getByText("ofx_ing_PLAINTEXT_ONCE")).toBeInTheDocument();
    expect(
      modal.getByText(/ne sera plus jamais affichée/),
    ).toBeInTheDocument();
    // web source → the script-tag snippet embeds the key and the endpoint
    expect(modal.getByText(/oriflux\.js/)).toBeInTheDocument();
    expect(modal.getByText(/data-key="ofx_ing_PLAINTEXT_ONCE"/)).toBeInTheDocument();

    await user.click(modal.getByRole("button", { name: "Fermer" }));
    expect(screen.queryByText("ofx_ing_PLAINTEXT_ONCE")).not.toBeInTheDocument();
    // the listing only ever shows the prefix
    expect(await screen.findByText("ofx_ing_abc…")).toBeInTheDocument();
  });

  it("issues and revokes an org read key", async () => {
    const user = userEvent.setup();
    renderApp("/settings/org");
    await user.type(await screen.findByLabelText("Nom de la clé"), "mcp");
    await user.click(screen.getByRole("button", { name: "Émettre une clé de lecture" }));

    const modal = within(await screen.findByRole("dialog"));
    expect(modal.getByText("ofx_read_PLAINTEXT_ONCE")).toBeInTheDocument();
    await user.click(modal.getByRole("button", { name: "Fermer" }));

    expect(await screen.findByText("ofx_read_xyz…")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Révoquer" }));
    expect(await screen.findByText("Révoquée")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Révoquer" })).not.toBeInTheDocument();
  });
});

describe("org settings — connect to Claude (MCP)", () => {
  it("shows the MCP endpoint and the one-click plugin install commands", async () => {
    renderApp("/settings/org");
    const heading = await screen.findByRole("heading", { name: "Connexion à Claude" });
    const panel = within(heading.closest("section")!);
    expect(panel.getByText("https://api.oriflux.sponge-theory.dev/mcp")).toBeInTheDocument();
    expect(panel.getByText(/\/plugin marketplace add ezeeFlop\/claude-plugins/)).toBeInTheDocument();
    expect(panel.getByText(/\/plugin install oriflux@sponge-theory/)).toBeInTheDocument();
  });

  it("offers a paste-ready mcpServers config with a read-key placeholder and a docs link", async () => {
    renderApp("/settings/org");
    const heading = await screen.findByRole("heading", { name: "Connexion à Claude" });
    const panel = within(heading.closest("section")!);
    expect(
      panel.getByText(/"url": "https:\/\/api\.oriflux\.sponge-theory\.dev\/mcp"/),
    ).toBeInTheDocument();
    expect(panel.getByText(/Bearer ofx_read_/)).toBeInTheDocument();
    expect(panel.getByRole("link", { name: "Guide API & MCP" })).toBeInTheDocument();
  });
});
