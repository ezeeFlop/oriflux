import assert from "node:assert/strict";
import { test } from "node:test";
import { Aggregator, bucketFor, LATENCY_BUCKETS_MS } from "./aggregator.js";

test("latency lands in log buckets", () => {
  assert.equal(bucketFor(0.4), 1);
  assert.equal(bucketFor(42), 50);
  assert.equal(bucketFor(999_999), LATENCY_BUCKETS_MS[LATENCY_BUCKETS_MS.length - 1]);
});

test("same key aggregates counts and histogram", () => {
  const agg = new Aggregator();
  for (const latency of [4, 5, 45]) {
    agg.record({ endpoint: "/v1/users/{id}", method: "GET", statusCode: 200,
                 ip: "1.2.3.4", latencyMs: latency });
  }
  const payload = agg.flush(new Date("2026-07-11T10:00:00Z"));
  assert.ok(payload);
  assert.equal(payload.entries.length, 1);
  assert.equal(payload.entries[0].count, 3);
  assert.deepEqual(payload.entries[0].latency_ms, { "5": 2, "50": 1 });
  assert.equal(payload.window_start, "2026-07-11T10:00:00.000Z");
});

test("flush drains the window", () => {
  const agg = new Aggregator();
  agg.record({ endpoint: "/a", method: "GET", statusCode: 200, latencyMs: 1 });
  assert.ok(agg.flush(new Date()));
  assert.equal(agg.flush(new Date()), null);
});

test("key cap collapses new IPs into an explicit overflow bucket", () => {
  const agg = new Aggregator(10);
  for (let i = 0; i < 25; i++) {
    agg.record({ endpoint: "/a", method: "GET", statusCode: 200,
                 ip: `10.0.0.${i}`, latencyMs: 2 });
  }
  const payload = agg.flush(new Date());
  assert.ok(payload);
  assert.equal(payload.overflow_count, 15);
  const overflow = payload.entries.filter((entry) => entry.overflow);
  assert.equal(overflow.length, 1);
  assert.equal(overflow[0].ip, ""); // IP dropped: geo shows unresolved server-side
  assert.equal(overflow[0].count, 15);
  assert.equal(payload.entries.length, 11);
});
