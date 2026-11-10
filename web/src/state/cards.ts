import type { Connection } from "@/api/events";
import type { Scorecard } from "@/api/snapshot";

/** One slot's card. `previous` is the last snapshot of the slot's earlier revision, kept so the
 * rows of a rebuilt revision can show the number they had before. */
export interface CardState {
  variantId: string;
  connection: Connection;
  snapshot: Scorecard | null;
  previous: Scorecard | null;
  refused: string | null;
}

export type CardsState = Readonly<Record<number, CardState>>;

export type CardsAction =
  | { type: "retarget"; slot: number; variantId: string }
  | { type: "snapshot"; slot: number; snapshot: Scorecard }
  | { type: "connection"; slot: number; variantId: string; connection: Connection }
  | { type: "refused"; slot: number; variantId: string; reason: string }
  | { type: "drop"; keep: readonly number[] };

export const cardsStart: CardsState = {};

export function cardsReducer(state: CardsState, action: CardsAction): CardsState {
  if (action.type === "drop") {
    const kept = Object.entries(state).filter(([slot]) => action.keep.includes(Number(slot)));
    return kept.length === Object.keys(state).length ? state : Object.fromEntries(kept);
  }
  const held = state[action.slot];
  switch (action.type) {
    case "retarget": {
      if (held?.variantId === action.variantId) return state;
      return {
        ...state,
        [action.slot]: {
          variantId: action.variantId,
          connection: "connecting",
          snapshot: null,
          previous: held ? (held.snapshot ?? held.previous) : null,
          refused: null,
        },
      };
    }
    case "snapshot": {
      if (held?.variantId !== action.snapshot.variant_id) return state;
      return { ...state, [action.slot]: { ...held, snapshot: action.snapshot, refused: null } };
    }
    case "connection": {
      if (held?.variantId !== action.variantId || held.connection === action.connection) return state;
      return { ...state, [action.slot]: { ...held, connection: action.connection } };
    }
    case "refused": {
      if (held?.variantId !== action.variantId) return state;
      return { ...state, [action.slot]: { ...held, refused: action.reason } };
    }
  }
}
