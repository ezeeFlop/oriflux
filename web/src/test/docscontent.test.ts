import { describe, expect, it } from "vitest";
import { docSlugs, getDoc, docTitle } from "../lib/docsContent";

describe("in-app docs content loader (#78)", () => {
  it("bundles the 6 public guides from docs/public", () => {
    expect(docSlugs).toEqual([
      "getting-started", "oriflux-js", "python-sdk", "api-mcp", "self-hosting", "privacy",
    ]);
  });
  it("returns locale content with es→en→fr fallback", () => {
    expect(getDoc("getting-started", "fr")).toContain("#");
    // es not generated yet → falls back to en (or fr)
    expect(getDoc("getting-started", "es")).toBeTruthy();
  });
  it("extracts the h1 title", () => {
    expect(docTitle("self-hosting", "fr")).toBe("Auto-hébergement");
  });
});
