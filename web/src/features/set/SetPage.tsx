import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useServices } from "@/app/context";
import { Gate } from "@/components/Gate";
import { TopBar } from "@/components/TopBar";
import { useResource } from "@/state/resource";
import { pinnedMaterial } from "./material";
import { Panes } from "./Panes";
import { SetReload } from "./reload";

export function SetPage() {
  const { api } = useServices();
  const { projectId = "", briefId = "" } = useParams();
  const [loaded, reload] = useResource(async () => {
    const [set, brief, materials] = await Promise.all([
      api.variantSet(projectId, briefId),
      api.brief(briefId),
      api.materials(),
    ]);
    return { set, brief, materials: materials.materials };
  }, `set:${projectId}:${briefId}`);
  const [picked, pick] = useState<string | null>(null);
  return (
    <SetReload value={reload}>
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
        {({ set, brief, materials }) => {
          const pinned = pinnedMaterial(brief, materials.map((one) => one.key));
          const material = pinned ?? picked ?? materials[0]?.key ?? null;
          return (
            <Panes
              key={material ?? ""}
              projectId={projectId}
              brief={brief}
              set={set}
              materials={materials}
              material={material}
              pinned={pinned !== null}
              onPick={pick}
            />
          );
        }}
      </Gate>
    </SetReload>
  );
}
