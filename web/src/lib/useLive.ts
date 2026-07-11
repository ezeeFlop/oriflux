/** Live WebSocket hook (issue #39): connects to /api/v1/live and returns
 *  the latest payload — or null, in which case callers keep their 10 s
 *  polling (a broken WS must never blank the live view). Reconnects with
 *  backoff; sends a keepalive ping every 20 s. */

import { useEffect, useRef, useState } from "react";
import { auth } from "./api";

export interface LivePayload {
  ts: string;
  projects: { id: string; name: string; live: number }[];
  pages: { page: string; value: number }[];
  countries: { country: string; value: number }[];
}

export function useLive(): LivePayload | null {
  const [payload, setPayload] = useState<LivePayload | null>(null);
  const attempts = useRef(0);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let ping: ReturnType<typeof setInterval> | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      if (closed || !auth.token || !auth.orgId) return;
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(
        `${scheme}://${window.location.host}/api/v1/live?token=${encodeURIComponent(
          auth.token,
        )}&org=${encodeURIComponent(auth.orgId)}`,
      );
      socket.onmessage = (event) => {
        attempts.current = 0;
        try {
          setPayload(JSON.parse(event.data) as LivePayload);
        } catch {
          /* malformed frame: ignore */
        }
      };
      socket.onclose = () => {
        setPayload(null); // callers fall back to polling immediately
        if (closed) return;
        attempts.current += 1;
        const backoff = Math.min(30_000, 1000 * 2 ** attempts.current);
        retry = setTimeout(connect, backoff);
      };
      socket.onerror = () => socket?.close();
      ping = setInterval(() => {
        if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
      }, 20_000);
    };

    connect();
    return () => {
      closed = true;
      if (ping) clearInterval(ping);
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, []);

  return payload;
}
