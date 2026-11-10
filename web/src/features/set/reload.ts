import { createContext, useContext } from "react";

/** Loads the variant set again without a page reload, for whatever learns that a slot got a new
 * revision. */
export const SetReload = createContext<() => void>(() => undefined);

export function useSetReload(): () => void {
  return useContext(SetReload);
}
