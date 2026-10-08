import React from "react";
import { createRoot } from "react-dom/client";
import { SetupGate } from "./setup/SetupGate";
import { DesktopFrame } from "./app/DesktopFrame";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DesktopFrame><SetupGate /></DesktopFrame>
  </React.StrictMode>
);
