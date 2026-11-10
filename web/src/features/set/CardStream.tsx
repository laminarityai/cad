import { useEffect, type Dispatch } from "react";
import { useServices } from "@/app/context";
import type { CardsAction } from "@/state/cards";

/** Keeps one slot's scorecard stream open while the slot shows `variantId`. Renders nothing. */
export function CardStream(props: {
  slot: number;
  variantId: string;
  materialKey: string;
  briefId: string;
  dispatch: Dispatch<CardsAction>;
}) {
  const { events } = useServices();
  const { slot, variantId, materialKey, briefId, dispatch } = props;
  useEffect(() => {
    dispatch({ type: "retarget", slot, variantId });
    return events.open(
      { variantId, materialKey, briefId },
      {
        onSnapshot: (snapshot) => {
          dispatch({ type: "snapshot", slot, snapshot });
        },
        onConnection: (connection) => {
          dispatch({ type: "connection", slot, variantId, connection });
        },
        onRefused: (reason) => {
          dispatch({ type: "refused", slot, variantId, reason });
        },
      },
    );
  }, [events, slot, variantId, materialKey, briefId, dispatch]);
  return null;
}
