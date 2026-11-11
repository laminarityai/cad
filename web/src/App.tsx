import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ProjectPage, ProjectsPage } from "@/features/projects/ProjectsPage";
import { SetPage } from "@/features/set/SetPage";
import { Home, Workspace } from "@/workspace/Workspace";

/* proto/project-workspace: the workspace replaces the pages; the old ones stay under before/. */
export function AppRoutes() {
  return (
    <Routes>
      <Route index element={<Home />} />
      <Route path="projects/:projectId" element={<Workspace />} />
      <Route path="before" element={<ProjectsPage />} />
      <Route path="before/projects/:projectId" element={<ProjectPage />} />
      <Route path="before/projects/:projectId/briefs/:briefId" element={<SetPage />} />
      <Route path="*" element={<Home />} />
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter basename="/app">
      <AppRoutes />
    </BrowserRouter>
  );
}
