import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { DigestPref, Member, ShareRow } from "../lib/api";
import { renderApp } from "./render";
import { server } from "./server";

let members: Member[];
let digest: DigestPref | null;
let shares: ShareRow[];

beforeEach(() => {
  members = [
    { user_id: "u1", email: "christophe@sponge-theory.io", name: "Christophe", role: "owner" },
  ];
  digest = null;
  shares = [];
  server.use(
    http.get("/api/v1/orgs/:orgId/members", () => HttpResponse.json(members)),
    http.post("/api/v1/orgs/:orgId/members", async ({ request }) => {
      const body = (await request.json()) as { email: string; role: Member["role"] };
      members = [...members, { user_id: `u${members.length + 1}`, name: "", ...body }];
      return HttpResponse.json({ user_id: "x", org_id: "org-1", role: body.role }, { status: 201 });
    }),
    http.get("/api/v1/orgs/:orgId/digest", () =>
      digest === null
        ? HttpResponse.json({ detail: "none" }, { status: 404 })
        : HttpResponse.json(digest),
    ),
    http.put("/api/v1/orgs/:orgId/digest", async ({ request }) => {
      digest = (await request.json()) as DigestPref;
      return HttpResponse.json(digest);
    }),
    http.delete("/api/v1/orgs/:orgId/digest", () => {
      digest = null;
      return new HttpResponse(null, { status: 204 });
    }),
    http.get("/api/v1/projects/:projectId/shares", () => HttpResponse.json(shares)),
    http.post("/api/v1/projects/:projectId/share", () => {
      const share = { id: `sh-${shares.length + 1}`, created_at: "2026-07-11T00:00:00Z", revoked: false };
      shares = [...shares, share];
      return HttpResponse.json(
        { id: share.id, token: "ofx_pub_SECRET", public_path: "/public/ofx_pub_SECRET" },
        { status: 201 },
      );
    }),
    http.delete("/api/v1/share/:shareId", ({ params }) => {
      shares = shares.map((s) => (s.id === params.shareId ? { ...s, revoked: true } : s));
      return new HttpResponse(null, { status: 204 });
    }),
  );
});

describe("org settings — members, digest, shares", () => {
  it("lists members and invites one with a role", async () => {
    const user = userEvent.setup();
    renderApp("/settings/org");
    expect(await screen.findByText("christophe@sponge-theory.io")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email du membre"), "bob@sponge-theory.io");
    await user.selectOptions(screen.getByLabelText("Rôle"), "admin");
    await user.click(screen.getByRole("button", { name: "Inviter" }));
    expect(await screen.findByText("bob@sponge-theory.io")).toBeInTheDocument();
    const row = screen.getByText("bob@sponge-theory.io").closest("li");
    expect(within(row as HTMLElement).getByText("Admin")).toBeInTheDocument();
  });

  it("shows the digest as off, subscribes, then unsubscribes", async () => {
    const user = userEvent.setup();
    renderApp("/settings/org");
    expect(
      await screen.findByText("Vous n'êtes pas abonné au digest de cette organisation."),
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Fréquence"), "monthly");
    await user.click(screen.getByRole("button", { name: "Enregistrer l'abonnement" }));
    expect(await screen.findByText(/Abonné — Mensuel/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Se désabonner" }));
    expect(
      await screen.findByText("Vous n'êtes pas abonné au digest de cette organisation."),
    ).toBeInTheDocument();
  });

  it("mints a share link (URL shown once), lists it, then revokes it", async () => {
    const user = userEvent.setup();
    renderApp("/settings/org");
    await user.click(await screen.findByRole("button", { name: "Créer un lien de partage" }));

    const modal = within(await screen.findByRole("dialog"));
    expect(modal.getByText(/\/public\/ofx_pub_SECRET/)).toBeInTheDocument();
    expect(modal.getByText(/ne sera plus jamais affichée/)).toBeInTheDocument();
    await user.click(modal.getByRole("button", { name: "Fermer" }));
    expect(screen.queryByText(/ofx_pub_SECRET/)).not.toBeInTheDocument();

    expect(await screen.findByText("sh-1")).toBeInTheDocument();
    const row = screen.getByText("sh-1").closest("li") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Révoquer" }));
    expect(await within(row).findByText("Révoquée")).toBeInTheDocument();
  });
});
