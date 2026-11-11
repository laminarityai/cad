import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Home, Start, Workspace } from "@/features/workspace/Workspace";

export function AppRoutes() {
  return (
    <Routes>
      <Route index element={<Home />} />
      <Route path="new" element={<Start />} />
      <Route path="projects/:projectId" element={<Workspace />} />
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
