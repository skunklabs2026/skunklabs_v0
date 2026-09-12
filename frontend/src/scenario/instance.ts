/** The application's scenario store, wired to the real backend. */

import { endpoints } from "../api";
import { post } from "../api/client";
import type { ScenarioCommandResult } from "./contract";
import { createScenarioStore } from "./store";

export const scenarioStore = createScenarioStore({
  openSocket: () => new WebSocket(endpoints.scenarioSocket()),
  send: (command, { engagementId, body }) =>
    post<ScenarioCommandResult>(
      endpoints.scenarioCommand(command, engagementId),
      body,
    ),
});
