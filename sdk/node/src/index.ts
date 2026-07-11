/**
 * oriflux-node — API analytics middleware for Express (PRD §5.3, issue #28).
 *
 * SDK-safety contract (the product-defining one): Oriflux downtime must
 * NEVER impact the instrumented app. Everything here is fire-and-forget —
 * short timeouts, a circuit breaker after consecutive failures, and every
 * code path wrapped so a bug in this file can never reach the request.
 */

import type { NextFunction, Request, Response } from "express";
import { Aggregator } from "./aggregator.js";

export { Aggregator, LATENCY_BUCKETS_MS } from "./aggregator.js";
export type { RecordArgs, WireEntry, WirePayload } from "./aggregator.js";

export interface OrifluxOptions {
  /** ofx_ing_… ingest key of the API source */
  apiKey: string;
  /** central ingest endpoint by default; override for first-party proxies */
  endpoint?: string;
  /** flush cadence — 60 s windows, like the Python SDK */
  flushIntervalMs?: number;
  /** derive a consumer id (API key id, tenant…) from the request */
  consumer?: (req: Request) => string;
  /** injectable for tests */
  fetchImpl?: typeof fetch;
  /** injectable clock for tests */
  now?: () => Date;
}

const DEFAULT_ENDPOINT = "https://in.oriflux.sponge-theory.dev";
const BREAKER_THRESHOLD = 3;
const BREAKER_COOLDOWN_MS = 60_000;

export function orifluxMiddleware(options: OrifluxOptions) {
  const aggregator = new Aggregator();
  const endpoint =
    (options.endpoint ?? DEFAULT_ENDPOINT).replace(/\/+$/, "") + "/api/v1/api-metrics";
  const fetchImpl = options.fetchImpl ?? fetch;
  const now = options.now ?? (() => new Date());
  let windowStart = now();
  let failures = 0;
  let breakerOpenUntil = 0;

  async function flush(): Promise<void> {
    const payload = aggregator.flush(windowStart);
    windowStart = now();
    if (!payload) return;
    if (Date.now() < breakerOpenUntil) return; // circuit open: drop silently
    try {
      const response = await fetchImpl(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${options.apiKey}`,
        },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok && response.status >= 500) throw new Error(`HTTP ${response.status}`);
      failures = 0;
    } catch {
      failures += 1;
      if (failures >= BREAKER_THRESHOLD) {
        breakerOpenUntil = Date.now() + BREAKER_COOLDOWN_MS;
        failures = 0;
      }
    }
  }

  const timer = setInterval(() => {
    void flush();
  }, options.flushIntervalMs ?? 60_000);
  timer.unref?.(); // never keep the process alive

  const middleware = (req: Request, res: Response, next: NextFunction): void => {
    const started = process.hrtime.bigint();
    res.on("finish", () => {
      try {
        const latencyMs = Number(process.hrtime.bigint() - started) / 1e6;
        const route = req.route?.path
          ? `${req.baseUrl ?? ""}${req.route.path}`
          : req.path;
        aggregator.record({
          endpoint: route,
          method: req.method,
          statusCode: res.statusCode,
          consumer: safeConsumer(options.consumer, req),
          ip: req.ip ?? req.socket?.remoteAddress ?? "",
          latencyMs,
          bytesIn: Number(req.headers["content-length"] ?? 0) || 0,
          bytesOut: Number(res.getHeader("content-length") ?? 0) || 0,
        });
      } catch {
        /* never impact the host app */
      }
    });
    next();
  };
  // exposed for tests and graceful shutdown
  middleware.flush = flush;
  middleware.stop = () => clearInterval(timer);
  return middleware as typeof middleware & { flush: () => Promise<void>; stop: () => void };
}

function safeConsumer(fn: ((req: Request) => string) | undefined, req: Request): string {
  if (!fn) return "";
  try {
    return fn(req) ?? "";
  } catch {
    return "";
  }
}
