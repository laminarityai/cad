import { Link, useParams } from "react-router-dom";
import { useServices } from "@/app/context";
import { Gate } from "@/components/Gate";
import { TopBar } from "@/components/TopBar";
import { useResource } from "@/state/resource";

const when = (iso: string) => new Date(iso).toLocaleString();

const ROW = "grid gap-1 border-t border-rule-2 px-4 py-3 first:border-t-0 hover:bg-muted sm:grid-cols-[1fr_auto]";

export function ProjectsPage() {
  const { api } = useServices();
  const { resource: projects } = useResource(() => api.projects(), "projects");
  return (
    <>
      <TopBar />
      <main className="mx-auto max-w-3xl p-4">
        <h1 className="mb-3 font-mono text-xs uppercase tracking-wider text-ink-2">Projects</h1>
        <Gate resource={projects}>
          {({ projects: list }) =>
            list.length === 0 ? (
              <p className="border border-border bg-panel p-4 text-ink-2">
                You have no projects yet. Ask the agent for a part and it opens one.
              </p>
            ) : (
              <ul className="border border-border bg-panel">
                {list.map((one) => (
                  <li key={one.project_id}>
                    <Link to={`/projects/${one.project_id}`} className={ROW}>
                      <span className="font-mono text-sm">{one.project_id}</span>
                      <span className="font-mono text-xs text-ink-3">
                        {String(one.brief_ids.length)} {one.brief_ids.length === 1 ? "brief" : "briefs"} · {when(one.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )
          }
        </Gate>
      </main>
    </>
  );
}

export function ProjectPage() {
  const { api } = useServices();
  const { projectId = "" } = useParams();
  const { resource: project } = useResource(() => api.project(projectId), `project:${projectId}`);
  return (
    <>
      <TopBar
        trail={
          <>
            <Link to="/">projects</Link> / {projectId}
          </>
        }
      />
      <main className="mx-auto max-w-3xl p-4">
        <h1 className="mb-3 font-mono text-xs uppercase tracking-wider text-ink-2">Briefs</h1>
        <Gate resource={project}>
          {({ briefs }) => (
            <ul className="border border-border bg-panel">
              {briefs.map((one) => (
                <li key={one.brief_id}>
                  <Link to={`/projects/${projectId}/briefs/${one.brief_id}`} className={ROW}>
                    <span className="font-mono text-sm">{one.brief_id}</span>
                    <span className="font-mono text-xs text-ink-3">
                      {one.confirmed_proposal === null
                        ? `${String(one.proposals)} proposed, none confirmed`
                        : `proposal ${String(one.confirmed_proposal)} confirmed`}{" "}
                      · {when(one.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Gate>
      </main>
    </>
  );
}
