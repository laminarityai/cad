import type { Saved } from "./state";

const KEY = "cad.chat.";
const LAST = "cad.chat.last.";

/** Browser storage can be off or full, so every read and write may fail and the page still works. */
function guarded<T>(body: () => T, otherwise: T): T {
  try {
    return body();
  } catch {
    return otherwise;
  }
}

export function loadSaved(conversationId: string): Saved | null {
  return guarded(() => {
    const raw = localStorage.getItem(KEY + conversationId);
    return raw === null ? null : (JSON.parse(raw) as Saved);
  }, null);
}

export function save(conversationId: string, saved: Saved): void {
  guarded(() => {
    localStorage.setItem(KEY + conversationId, JSON.stringify(saved));
  }, undefined);
}

export function lastConversation(projectId: string, briefId: string): string | null {
  return guarded(() => localStorage.getItem(`${LAST}${projectId}.${briefId}`), null);
}

export function rememberConversation(projectId: string, briefId: string, conversationId: string): void {
  guarded(() => {
    localStorage.setItem(`${LAST}${projectId}.${briefId}`, conversationId);
  }, undefined);
}
