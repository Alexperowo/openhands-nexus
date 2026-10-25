import "./init"; // MUST BE FIRST
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";
import "@openhands/agent-canvas/styles.css";
import "./index.css";
import "./motion.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
