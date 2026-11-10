import { useSyncExternalStore } from "react";

function subscribe(changed: () => void): () => void {
  document.addEventListener("visibilitychange", changed);
  return () => {
    document.removeEventListener("visibilitychange", changed);
  };
}

/** Whether this tab is on screen. A page holds its long-lived streams only while it is: over
 * HTTP/1.1 a browser opens 6 connections per host, so two set tabs that each held a chat stream
 * and three scorecard streams left no connection for a Stop pressed in either. */
export function useVisible(): boolean {
  return useSyncExternalStore(subscribe, () => document.visibilityState === "visible");
}
