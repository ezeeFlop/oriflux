/**
 * Client-side 60 s aggregation window (Apitally pattern, PRD §5.3) —
 * the exact wire semantics of the Python oriflux-sdk. Requests are keyed
 * by (endpoint template, method, status code, consumer, caller IP); the
 * IP in the key is what makes API geo possible despite pre-aggregation
 * (ingest resolves then discards it). Past `maxKeys` distinct keys, NEW
 * keys collapse into one overflow bucket per (endpoint, method, status,
 * consumer) with the IP dropped — the data stays honest about itself.
 */

export const LATENCY_BUCKETS_MS: readonly number[] = [
  1, 2, 3, 5, 8, 13, 20, 30, 50, 80, 130, 200, 300, 500, 800,
  1300, 2000, 3000, 5000, 8000, 13000, 20000, 30000,
];

export interface WireEntry {
  endpoint: string;
  method: string;
  status_code: number;
  consumer: string;
  ip: string;
  count: number;
  bytes_in: number;
  bytes_out: number;
  latency_ms: Record<string, number>;
  overflow: boolean;
}

export interface WirePayload {
  window_start: string;
  overflow_count: number;
  entries: WireEntry[];
}

interface Cell {
  endpoint: string;
  method: string;
  statusCode: number;
  consumer: string;
  ip: string;
  count: number;
  bytesIn: number;
  bytesOut: number;
  histogram: Map<number, number>;
  overflow: boolean;
}

export function bucketFor(latencyMs: number): number {
  for (const bucket of LATENCY_BUCKETS_MS) {
    if (latencyMs <= bucket) return bucket;
  }
  return LATENCY_BUCKETS_MS[LATENCY_BUCKETS_MS.length - 1];
}

export interface RecordArgs {
  endpoint: string;
  method: string;
  statusCode: number;
  consumer?: string;
  ip?: string;
  latencyMs: number;
  bytesIn?: number;
  bytesOut?: number;
}

export class Aggregator {
  private window = new Map<string, Cell>();
  private overflowCount = 0;

  constructor(private readonly maxKeys = 2000) {}

  record(args: RecordArgs): void {
    const consumer = args.consumer ?? "";
    let ip = args.ip ?? "";
    let overflow = false;
    let mapKey = [args.endpoint, args.method, args.statusCode, consumer, ip].join("|");
    if (!this.window.has(mapKey) && this.window.size >= this.maxKeys) {
      // collapse: drop the IP, mark the entry — geo shows unresolved server-side
      overflow = true;
      ip = "";
      this.overflowCount += 1;
      mapKey = [args.endpoint, args.method, args.statusCode, consumer, "<overflow>"].join("|");
    }
    let cell = this.window.get(mapKey);
    if (!cell) {
      cell = {
        endpoint: args.endpoint,
        method: args.method,
        statusCode: args.statusCode,
        consumer,
        ip,
        count: 0,
        bytesIn: 0,
        bytesOut: 0,
        histogram: new Map(),
        overflow,
      };
      this.window.set(mapKey, cell);
    }
    cell.count += 1;
    cell.bytesIn += args.bytesIn ?? 0;
    cell.bytesOut += args.bytesOut ?? 0;
    const bucket = bucketFor(args.latencyMs);
    cell.histogram.set(bucket, (cell.histogram.get(bucket) ?? 0) + 1);
  }

  /** Drain the window into the ingest wire payload (or null when empty). */
  flush(windowStart: Date): WirePayload | null {
    if (this.window.size === 0) return null;
    const entries: WireEntry[] = [];
    for (const cell of this.window.values()) {
      const latency: Record<string, number> = {};
      for (const [bucket, count] of cell.histogram) latency[String(bucket)] = count;
      entries.push({
        endpoint: cell.endpoint.slice(0, 200),
        method: cell.method.slice(0, 16),
        status_code: cell.statusCode,
        consumer: cell.consumer.slice(0, 128),
        ip: cell.ip.slice(0, 64),
        count: cell.count,
        bytes_in: cell.bytesIn,
        bytes_out: cell.bytesOut,
        latency_ms: latency,
        overflow: cell.overflow,
      });
    }
    const payload: WirePayload = {
      window_start: windowStart.toISOString(),
      overflow_count: this.overflowCount,
      entries: entries.slice(0, 4000),
    };
    this.window.clear();
    this.overflowCount = 0;
    return payload;
  }
}
