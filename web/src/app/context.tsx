import { createContext, useContext, type ReactNode } from "react";
import { httpApi, type Api } from "@/api/client";
import { serverEvents, type ScorecardEvents } from "@/api/events";
import { threeCadViewer, type ViewerEngine } from "@/features/viewer/engine";

export interface Services {
  api: Api;
  events: ScorecardEvents;
  viewer: ViewerEngine;
}

const Context = createContext<Services>({ api: httpApi, events: serverEvents, viewer: threeCadViewer });

export function ServicesProvider({ services, children }: { services: Services; children: ReactNode }) {
  return <Context value={services}>{children}</Context>;
}

export function useServices(): Services {
  return useContext(Context);
}
