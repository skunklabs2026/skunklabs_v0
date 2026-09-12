/**
 * React access to the scenario store.
 *
 * Components take the store from context rather than importing the singleton:
 * App provides the real one (scenario/instance.ts), a test provides its own.
 */

import { createContext, useContext, useMemo, useSyncExternalStore } from "react";
import type { ScenarioState, ScenarioStore } from "./store";

const StoreContext = createContext<ScenarioStore | null>(null);

export const ScenarioStoreProvider = StoreContext.Provider;

export function useScenarioStore(): ScenarioStore {
  const store = useContext(StoreContext);
  if (!store) throw new Error("Scenario hooks need a <ScenarioStoreProvider>.");
  return store;
}

/** The whole scenario state. Re-renders on every published snapshot. */
export function useScenario(): ScenarioState {
  const store = useScenarioStore();
  return useSyncExternalStore(store.subscribe, store.getState);
}

/**
 * One derived value. Re-renders only when it changes, so `select` must return
 * a primitive or a stable reference.
 */
export function useScenarioValue<T>(select: (state: ScenarioState) => T): T {
  const store = useScenarioStore();
  return useSyncExternalStore(store.subscribe, () => select(store.getState()));
}

export interface ScenarioCommands {
  configure: (body: {
    scenario_id?: string;
    latitude?: number;
    longitude?: number;
  }) => void;
  start: () => void;
  authorize: (engagementId: string, interceptors: number) => void;
  decline: (engagementId: string) => void;
  /** Give a proposed response to a different node. */
  reassign: (engagementId: string, nodeId: string) => void;
  reset: () => void;
  setInterceptorRequest: (engagementId: string, count: number) => void;
  selectNode: (nodeId: string | null) => void;
}

export function useScenarioCommands(): ScenarioCommands {
  const store = useScenarioStore();
  return useMemo(
    () => ({
      configure: (body) => void store.command("configure", { body }),
      start: () => void store.command("start"),
      authorize: (engagementId, interceptors) =>
        void store.command("authorize", { engagementId, body: { interceptors } }),
      decline: (engagementId) => void store.command("decline", { engagementId }),
      reassign: (engagementId, nodeId) =>
        void store.command("reassign", { engagementId, body: { node_id: nodeId } }),
      reset: () => void store.command("reset"),
      setInterceptorRequest: (engagementId, count) =>
        store.setInterceptorRequest(engagementId, count),
      selectNode: (nodeId) => store.selectNode(nodeId),
    }),
    [store],
  );
}
