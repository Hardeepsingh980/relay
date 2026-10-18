"use client";

import { useEffect, useRef } from "react";

import { API_BASE } from "./api";
import type { BatonEvent } from "./types";

/** Subscribe to a Relay SSE stream. EventSource resumes with Last-Event-ID on reconnect. */
export function useEvents(path: string | null, onEvent: (e: BatonEvent) => void, onEnd?: () => void) {
  const handler = useRef(onEvent);
  const end = useRef(onEnd);
  useEffect(() => {
    handler.current = onEvent;
    end.current = onEnd;
  });
  useEffect(() => {
    if (!path) return;
    const es = new EventSource(`${API_BASE}${path}`, { withCredentials: true });
    const seen = new Set<string>();
    es.onmessage = (m) => {
      try {
        const ev = JSON.parse(m.data) as BatonEvent;
        if (seen.has(ev.eventId)) return; // idempotent on reconnect
        seen.add(ev.eventId);
        handler.current(ev);
        if (ev.type === "analysis.completed" || ev.type === "analysis.failed") {
          es.close();
          end.current?.();
        }
      } catch {
        /* ignore keep-alives */
      }
    };
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) end.current?.();
    };
    return () => es.close();
  }, [path]);
}
