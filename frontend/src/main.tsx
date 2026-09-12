import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

// Brand faces, bundled locally rather than fetched from Google Fonts - the
// console must render identically with no network connection.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";

import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/console.css";
// The sensor lab (#/sensor-lab) imports its own stylesheets when opened.

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
