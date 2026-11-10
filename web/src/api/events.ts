import { restore, type Scorecard } from "./snapshot";
import type { ScorecardSnapshot } from "./types";

export type Connection = "connecting" | "live" | "reconnecting" | "closed";

export interface CardQuery {
  variantId: string;
  materialKey: string;
  briefId: string;
}

export interface CardHandlers {
  onSnapshot(snapshot: Scorecard): void;
  onConnection(connection: Connection): void;
  onRefused(reason: string): void;
}

/** One variant's scorecard as the server pushes it. `open` returns the function that closes it. */
export interface ScorecardEvents {
  open(query: CardQuery, handlers: CardHandlers): () => void;
}

export function eventsUrl(query: CardQuery): string {
  const params = new URLSearchParams({ material_key: query.materialKey, brief_id: query.briefId });
  return `/v1/variants/${encodeURIComponent(query.variantId)}/events?${params.toString()}`;
}

/** The server's `GET /v1/variants/{variant_id}/events`: each `scorecard` event is a whole
 * `Scorecard`, the stream ends with a `refused` event, and the browser reconnects on its own. */
export const serverEvents: ScorecardEvents = {
  open(query, handlers) {
    const source = new EventSource(eventsUrl(query), { withCredentials: true });
    handlers.onConnection("connecting");
    source.onopen = () => {
      handlers.onConnection("live");
    };
    source.onerror = () => {
      handlers.onConnection(source.readyState === EventSource.CLOSED ? "closed" : "reconnecting");
    };
    source.addEventListener("scorecard", (event) => {
      handlers.onSnapshot(restore(JSON.parse((event as MessageEvent<string>).data) as ScorecardSnapshot));
    });
    source.addEventListener("refused", (event) => {
      source.close();
      handlers.onConnection("closed");
      handlers.onRefused((event as MessageEvent<string>).data);
    });
    return () => {
      source.close();
    };
  },
};
