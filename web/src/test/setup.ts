/** Test harness setup — the single seam is HTTP: MSW fakes /api/v1/* and
 *  everything above it (views, router, react-query) runs for real. */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";
import i18n from "../i18n";
import { server } from "./server";

// jsdom lacks WebSocket: a silent stub keeps useLive() inert (payload stays
// null, views fall back to polling — exactly the production degraded mode).
class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  readyState = FakeWebSocket.CONNECTING;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {}
  send(): void {}
  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }
}
Object.assign(globalThis, { WebSocket: FakeWebSocket });

// jsdom lacks ResizeObserver (recharts ResponsiveContainer needs it).
class FakeResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
Object.assign(globalThis, { ResizeObserver: FakeResizeObserver });

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  void i18n.changeLanguage("fr");
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => server.close());
