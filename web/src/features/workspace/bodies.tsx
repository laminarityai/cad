import { useState } from "react";
import { useServices } from "@/app/context";
import type { DoneCheck, Scorecard } from "@/api/snapshot";
import { useResource } from "@/state/resource";

export interface BodyLine {
  name: string;
  colour: string | null;
  material: string;
  chosenBy: "you" | "agent";
  solids: number;
  measured: string;
}

const VIEW_POLL_MS = 1500;

const three = (magnitude: number) => String(Number(magnitude.toPrecision(3)));

function amount(one: { magnitude: number; unit: string } | undefined, what: string): string {
  if (!one) return `${what} not measured`;
  if (one.unit === "mm³") return `${three(one.magnitude / 1000)} cm³`;
  return one.unit === "kg" ? `${three(one.magnitude * 1000)} g` : `${three(one.magnitude)} ${one.unit}`;
}

export function bodiesOf(snapshot: Scorecard, colours: ReadonlyMap<string, string>): BodyLine[] {
  const weighed = snapshot.results.find((one): one is DoneCheck => !("kind" in one) && one.check_id === "mass");
  const read = (name: string) => weighed?.measured.find((one) => one.name === name)?.value;
  return snapshot.bodies.map((body) => {
    const made = snapshot.body_materials.find((one) => one.body === body.name);
    const solids = body.solids.length;
    return {
      name: body.name,
      colour: colours.get(body.name) ?? null,
      material: made?.key ?? "no material",
      chosenBy: made?.set_by.kind === "agent_argument" ? "agent" : "you",
      solids,
      measured: `${amount(read(`volume:${body.name}`), "volume")} · ${amount(read(`mass:${body.name}`), "mass")}`,
    };
  });
}

function useViewUntilMeshed(variantId: string) {
  const { api } = useServices();
  const [meshed, setMeshed] = useState(false);
  const { resource } = useResource(() => api.view(variantId), variantId, meshed ? undefined : VIEW_POLL_MS);
  const view = resource.status === "ok" ? resource.data : null;
  if (!meshed && view !== null && view.mesh !== "pending") setMeshed(true);
  return view;
}

function useColours(variantId: string): ReadonlyMap<string, string> {
  const view = useViewUntilMeshed(variantId);
  return new Map((view?.areas ?? []).map((one) => [one.name, one.colour]));
}

export function BodyRows({ snapshot }: { snapshot: Scorecard }) {
  const lines = bodiesOf(snapshot, useColours(snapshot.variant_id));
  return (
    <>
      <h3 className="px-4 pb-1 pt-2 text-[13px] font-medium text-ink-3">Bodies</h3>
      <ul aria-label="Bodies">
        {lines.map((one) => (
          <li key={one.name} data-body={one.name} className="flex items-start gap-2.5 border-b border-rule-2 px-4 py-2 last:border-b-0">
            <span
              aria-hidden
              data-swatch={one.colour ?? undefined}
              className="mt-1 inline-block size-3 shrink-0 rounded-sm ring-1 ring-rule"
              style={one.colour ? { backgroundColor: one.colour } : undefined}
            />
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[15px]">{one.name}</span>
                <span className="shrink-0 font-mono text-[13px] tabular-nums text-ink-2">{one.measured}</span>
              </span>
              <span className="block truncate text-[13px] text-ink-3">
                {`${one.material} · ${one.chosenBy === "agent" ? "chosen by the agent" : "from your words"} · ${String(one.solids)} ${one.solids === 1 ? "solid" : "solids"}`}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}
