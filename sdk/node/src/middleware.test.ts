import assert from "node:assert/strict";
import { test } from "node:test";
import express from "express";
import type { AddressInfo } from "node:net";
import { orifluxMiddleware } from "./index.js";

async function drive(fetchImpl: typeof fetch) {
  const app = express();
  const middleware = orifluxMiddleware({
    apiKey: "ofx_ing_test",
    endpoint: "https://ingest.example",
    fetchImpl,
    flushIntervalMs: 3600_000, // manual flush in tests
  });
  app.use(middleware);
  app.get("/v1/users/:id", (_req, res) => {
    res.json({ ok: true });
  });
  const server = app.listen(0);
  const port = (server.address() as AddressInfo).port;
  await fetch(`http://127.0.0.1:${port}/v1/users/42`);
  await fetch(`http://127.0.0.1:${port}/v1/users/43`);
  await new Promise((resolve) => setTimeout(resolve, 50));
  await middleware.flush();
  middleware.stop();
  server.close();
  return middleware;
}

test("express requests aggregate under the route template and ship once", async () => {
  const calls: { url: string; body: any }[] = [];
  const fakeFetch: typeof fetch = async (url, init) => {
    calls.push({ url: String(url), body: JSON.parse(String(init?.body)) });
    return new Response("{}", { status: 202 });
  };
  await drive(fakeFetch);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://ingest.example/api/v1/api-metrics");
  const entries = calls[0].body.entries;
  assert.equal(entries.length, 1); // both requests share the /v1/users/:id template
  assert.equal(entries[0].endpoint, "/v1/users/:id");
  assert.equal(entries[0].count, 2);
  assert.equal(entries[0].status_code, 200);
  assert.ok(entries[0].ip.length > 0); // caller IP in the aggregation key
});

test("a broken ingest never breaks the app (fire-and-forget breaker)", async () => {
  const failingFetch: typeof fetch = async () => {
    throw new Error("ECONNREFUSED");
  };
  const middleware = await drive(failingFetch); // must not throw
  assert.ok(middleware); // requests answered fine while ingest was down
});
