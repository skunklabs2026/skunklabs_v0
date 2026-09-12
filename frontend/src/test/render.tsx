import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { ScenarioStoreProvider } from "../scenario/hooks";
import type { ScenarioStore } from "../scenario/store";

export function renderWithStore(ui: ReactElement, store: ScenarioStore) {
  return render(<ScenarioStoreProvider value={store}>{ui}</ScenarioStoreProvider>);
}
