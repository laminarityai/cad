import { useEffect, useReducer, useState, type ReactNode } from "react";
import type { BriefView, MaterialListings, VariantSetView } from "@/api/types";
import { Scorecard } from "@/features/scorecard/Scorecard";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cardsReducer, cardsStart } from "@/state/cards";
import { CardStream } from "./CardStream";
import { MemberTile } from "./MemberTile";
import { WaitingPanel } from "./WaitingPanel";
import { useNarrow } from "./useNarrow";

const SECTION = "font-mono text-[10.5px] uppercase tracking-wider text-ink-2";

/** Who chose the material the scorecards are for: the brief's confirmed made_of requirement, the
 * person with the picker, or nobody, when the page fell back to the first row of the table. */
export type ChosenBy = "brief" | "person" | "default";

function MaterialPicker(props: {
  materials: MaterialListings["materials"];
  value: string | null;
  chosenBy: Exclude<ChosenBy, "brief">;
  onChange: (key: string) => void;
}) {
  return (
    <div className="border border-border bg-panel px-2.5 py-1.5">
      <label className="flex items-center justify-between gap-2">
        <span className={SECTION}>Material</span>
        <select
          value={props.value ?? ""}
          onChange={(event) => {
            props.onChange(event.target.value);
          }}
          className="min-w-0 border border-border bg-panel-2 px-1.5 py-1 font-mono text-xs"
        >
          {props.materials.map((one) => (
            <option key={one.key} value={one.key}>
              {one.name}
            </option>
          ))}
        </select>
      </label>
      {props.chosenBy === "default" ? (
        <p data-material-default className="pt-1.5 text-xs text-wait">
          The brief confirms no material, so these scorecards use the first one in the table. Pick the one you mean.
        </p>
      ) : null}
    </div>
  );
}

export function Panes(props: {
  projectId: string;
  brief: BriefView;
  set: VariantSetView;
  materials: MaterialListings["materials"];
  material: string | null;
  chosenBy: ChosenBy;
  onPick: (key: string) => void;
  run: ReactNode;
  chat: ReactNode;
}) {
  const { projectId, brief, set, materials, material, chosenBy, onPick, run, chat } = props;
  const narrow = useNarrow();
  const [cards, dispatch] = useReducer(cardsReducer, cardsStart);
  const [chosen, choose] = useState<number | null>(null);
  const slots = set.members.map((one) => one.slot);
  const slotsKey = slots.join(",");
  useEffect(() => {
    dispatch({ type: "drop", keep: slotsKey === "" ? [] : slotsKey.split(",").map(Number) });
  }, [slotsKey]);
  const selected = set.members.find((one) => one.slot === chosen) ?? set.members[0];

  const members: ReactNode =
    set.members.length === 0 ? (
      <p className="border border-border bg-panel p-4 text-ink-2">
        No variants yet. Once you confirm the requirements, the agent builds them here.
      </p>
    ) : (
      <div className="grid auto-rows-[minmax(280px,1fr)] gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr))]">
        {set.members.map((member) => (
          <MemberTile
            key={member.slot}
            member={member}
            card={cards[member.slot]}
            selected={member.slot === selected?.slot}
            onSelect={() => {
              choose(member.slot);
            }}
          />
        ))}
      </div>
    );

  const model = (
    <div className="flex flex-col gap-2.5">
      {run}
      {members}
    </div>
  );

  const side: ReactNode = (
    <div className="flex flex-col gap-2.5">
      <WaitingPanel brief={brief} projectId={projectId} />
      {chosenBy !== "brief" && materials.length > 0 ? (
        <MaterialPicker materials={materials} value={material} chosenBy={chosenBy} onChange={onPick} />
      ) : null}
      <Scorecard
        card={selected ? cards[selected.slot] : undefined}
        heading={selected ? `Scorecard · slot ${String(selected.slot)} · revision ${String(selected.revision)}` : "Scorecard"}
      />
    </div>
  );

  const streams = material
    ? set.members.map((member) => (
        <CardStream
          key={member.slot}
          slot={member.slot}
          variantId={member.variant_id}
          materialKey={material}
          briefId={set.brief_id}
          dispatch={dispatch}
        />
      ))
    : null;

  if (narrow) {
    return (
      <>
        {streams}
        <Tabs defaultValue="model" className="min-h-0">
          <TabsList>
            <TabsTrigger value="chat">Chat</TabsTrigger>
            <TabsTrigger value="model">Model</TabsTrigger>
            <TabsTrigger value="scorecard">Scorecard</TabsTrigger>
          </TabsList>
          <TabsContent value="chat" className="p-2.5">
            {chat}
          </TabsContent>
          <TabsContent value="model" className="p-2.5">
            {model}
          </TabsContent>
          <TabsContent value="scorecard" className="p-2.5">
            {side}
          </TabsContent>
        </Tabs>
      </>
    );
  }
  return (
    <>
      {streams}
      <div className="grid h-[calc(100vh-38px)] min-h-[620px] grid-cols-[minmax(320px,420px)_minmax(0,1fr)_minmax(280px,360px)] gap-2.5 p-2.5">
        <div className="min-h-0 overflow-y-auto">{side}</div>
        <div className="min-h-0 overflow-y-auto">{model}</div>
        <div className="min-h-0">{chat}</div>
      </div>
    </>
  );
}
