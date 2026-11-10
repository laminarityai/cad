import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ProjectPage, ProjectsPage } from "@/features/projects/ProjectsPage";
import { SetPage } from "@/features/set/SetPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route index element={<ProjectsPage />} />
      <Route path="projects/:projectId" element={<ProjectPage />} />
      <Route path="projects/:projectId/briefs/:briefId" element={<SetPage />} />
      <Route path="*" element={<ProjectsPage />} />
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
