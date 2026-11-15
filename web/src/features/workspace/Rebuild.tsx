import { useState } from "react";
import { useServices } from "@/app/context";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/busy";
import { toast } from "@/components/ui/toaster";
import type { Rebuildable } from "@/features/viewer/useMesh";
import { said } from "@/state/resource";
import type { Card } from "./cards";

export const OUTDATED_WORDS = "This option was built before an app update.";
const WORDS: Readonly<Record<Rebuildable, string>> = {
  outdated: `${OUTDATED_WORDS} Rebuild it to see it and its checks.`,
  damaged: "This option's stored files do not match its build. Rebuild it from its code, or ask in the chat to build it again.",
};

export const isOutdated = (card: Card | undefined): boolean => card?.snapshot === null && card.missing === "outdated";

/** Builds the option again from its stored code and checks it, which takes about as long as the first build. */
export function Rebuild(props: { variantId: string; briefId: string; why: Rebuildable; onRebuilt: () => void }) {
  const { variantId, briefId, why, onRebuilt } = props;
  const { api } = useServices();
  const [working, setWorking] = useState(false);
  const rebuild = () => {
    setWorking(true);
    api.rebuild(variantId, briefId).then(
      () => {
        setWorking(false);
        onRebuilt();
      },
      (error: unknown) => {
        setWorking(false);
        toast.error(said(error));
      },
    );
  };
  return (
    <div data-outdated className="flex flex-col items-start gap-3 px-4 pb-4 pt-14 text-[15px] text-ink-2">
      <p>{WORDS[why]}</p>
      <Button type="button" variant="accent" disabled={working} onClick={rebuild}>
        {working ? <Spinner /> : null}
        {working ? "Rebuilding" : "Rebuild"}
      </Button>
    </div>
  );
}
