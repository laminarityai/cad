import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { Crashed } from "./components/Crashed";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");
createRoot(root).render(
  <StrictMode>
    <Crashed>
      <App />
    </Crashed>
  </StrictMode>,
);
