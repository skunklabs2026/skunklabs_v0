import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

// Brand faces, bundled locally rather than fetched from Google Fonts — the
// console must render identically with no network connection.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";

import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/setup.css";
import "./styles/operator.css";
// Last: it overrides the screen layouts above at each breakpoint.
import "./styles/responsive.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
