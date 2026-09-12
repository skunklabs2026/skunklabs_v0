import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { fakeStore, makeSnapshot } from "../test/fixtures";
import {
  ScenarioStoreProvider,
  useScenario,
  useScenarioCommands,
  useScenarioStore,
  useScenarioValue,
} from "./hooks";
import type { ScenarioStore } from "./store";

const withStore =
  (store: ScenarioStore) =>
  ({ children }: { children: ReactNode }) => (
    <ScenarioStoreProvider value={store}>{children}</ScenarioStoreProvider>
  );

describe("scenario hooks", () => {
  it("require a provider", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useScenarioStore())).toThrow(
      /ScenarioStoreProvider/,
    );
    vi.restoreAllMocks();
  });

  it("follow the store", () => {
    const { store, set } = fakeStore();
    const { result } = renderHook(() => useScenario(), {
      wrapper: withStore(store),
    });
    expect(result.current.snapshot).toBeNull();
    set({ snapshot: makeSnapshot({ revision: 7 }) });
    expect(result.current.snapshot?.revision).toBe(7);
  });

  it("re-render a selected value only when it changes", () => {
    const { store, set } = fakeStore({ snapshot: makeSnapshot() });
    let renders = 0;
    const { result } = renderHook(
      () => {
        renders += 1;
        return useScenarioValue((s) => s.snapshot?.nodes.length ?? 0);
      },
      { wrapper: withStore(store) },
    );
    expect(result.current).toBe(6);

    const before = renders;
    set({ snapshot: makeSnapshot({ elapsed_s: 3 }) });
    expect(renders).toBe(before);

    set({ snapshot: makeSnapshot({ nodes: [] }) });
    expect(result.current).toBe(0);
  });

  it("send every operator command through the store", () => {
    const { store, command } = fakeStore();
    const { result } = renderHook(() => useScenarioCommands(), {
      wrapper: withStore(store),
    });
    result.current.configure({ scenario_id: "S2" });
    result.current.start();
    result.current.authorize("R-01", 2);
    result.current.decline("R-02");
    result.current.reset();
    expect(command.mock.calls).toEqual([
      ["configure", { body: { scenario_id: "S2" } }],
      ["start"],
      ["authorize", { engagementId: "R-01", body: { interceptors: 2 } }],
      ["decline", { engagementId: "R-02" }],
      ["reset"],
    ]);
  });

  it("hold the operator's local choices", () => {
    const { store } = fakeStore();
    const { result } = renderHook(() => useScenarioCommands(), {
      wrapper: withStore(store),
    });
    result.current.setInterceptorRequest("R-01", 3);
    result.current.selectNode("NODE-04");
    expect(store.getState().interceptorRequests).toEqual({ "R-01": 3 });
    expect(store.getState().selectedNodeId).toBe("NODE-04");
  });
});
