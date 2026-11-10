import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useServices } from "@/app/context";
import { ChatPanel } from "@/chat/ChatPanel";
import { useConversation } from "@/chat/useConversation";
import { RunStatus } from "@/mode/RunStatus";
import { Gate } from "@/components/Gate";
import { TopBar } from "@/components/TopBar";
import { useResource } from "@/state/resource";
import { pinnedMaterial } from "./material";
import { Panes } from "./Panes";

/** How long after one read of the set the page reads it again. A rebuilt slot gets a new variant
 * id, and only the set names it: the scorecard stream of the old id never hears of it. */
export const FOLLOW_MS = 2000;

export function SetPage() {
  const { api } = useServices();
  const { projectId = "", briefId = "" } = useParams();
  const { resource: loaded, reload } = useResource(async () => {
    const [set, brief, materials, waiting] = await Promise.all([
      api.variantSet(projectId, briefId),
      api.brief(briefId),
      api.materials(),
      api.waiting(projectId),
    ]);
    return { set, brief, materials: materials.materials, waiting };
  }, `set:${projectId}:${briefId}`, FOLLOW_MS);
  const chat = useConversation(projectId, briefId, reload);
  const [picked, pick] = useState<string | null>(null);
  return (
    <>
      <TopBar
        trail={
          <>
            <Link to="/">projects</Link> / <Link to={`/projects/${projectId}`}>{projectId}</Link> / {briefId}
          </>
        }
      >
        {loaded.status === "ok" ? (
          <p className="truncate font-mono text-xs text-ink-2" title={loaded.data.brief.text}>
            <q className="text-ink">{loaded.data.brief.text}</q>
          </p>
        ) : null}
      </TopBar>
      <Gate resource={loaded}>
        {({ set, brief, materials, waiting }) => {
          const pinned = pinnedMaterial(brief, materials.map((one) => one.key));
          const material = pinned ?? picked ?? materials[0]?.key ?? null;
          return (
            <Panes
              key={material ?? ""}
              projectId={projectId}
              waiting={waiting}
              set={set}
              materials={materials}
              material={material}
              chosenBy={pinned !== null ? "brief" : picked !== null ? "person" : "default"}
              onPick={pick}
              run={<RunStatus mode={chat.mode} run={chat.run} onStop={() => void chat.stop()} />}
              chat={<ChatPanel chat={chat} />}
            />
          );
        }}
      </Gate>
    </>
  );
}
