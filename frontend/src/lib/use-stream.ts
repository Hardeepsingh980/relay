"use client";

import { useEffect, useReducer, useRef } from "react";

import { API_BASE } from "./api";
import type { StreamEvent } from "./relay";

/**
 * Subscribe to an in-memory event log (investigations, live calls). The server replays
 * every event from the start, so a reducer can rebuild the whole view from the stream;
 * EventSource resumes with Last-Event-ID after a dropped connection.
 */
export function useStream<S>(
  path: string | null,
  reducer: (state: S, ev: StreamEvent) => S,
  initial: S,
): [S, { connected: boolean; ended: boolean }] {
  const [state, dispatch] = useReducer((s: { v: S; seen: number; connected: boolean; ended: boolean }, a: { ev?: StreamEvent; status?: "open" | "end" | "reset" }) => {
    if (a.status === "reset") return { v: initial, seen: -1, connected: false, ended: false };
    if (a.status === "open") return { ...s, connected: true };
    if (a.status === "end") return { ...s, ended: true, connected: false };
    if (!a.ev || a.ev.id <= s.seen) return s;
    return { ...s, v: reducer(s.v, a.ev), seen: a.ev.id };
  }, { v: initial, seen: -1, connected: false, ended: false });
  const pathRef = useRef(path);

  useEffect(() => {
    if (pathRef.current !== path) {
      pathRef.current = path;
      dispatch({ status: "reset" });
    }
    if (!path) return;
    const es = new EventSource(`${API_BASE}${path}`, { withCredentials: true });
    es.onopen = () => dispatch({ status: "open" });
    es.onmessage = (m) => {
      try {
        dispatch({ ev: JSON.parse(m.data) as StreamEvent });
      } catch {
        /* keep-alive */
      }
    };
    es.addEventListener("end", () => {
      es.close();
      dispatch({ status: "end" });
    });
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) dispatch({ status: "end" });
    };
    return () => es.close();
  }, [path]);
  return [state.v, { connected: state.connected, ended: state.ended }];
}
