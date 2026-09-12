import { describe, expect, it } from "vitest";
import {
  makeDecisionSnapshot,
  makeEngagement,
  makeInterceptor,
  makeNode,
  makeSnapshot,
  makeTrack,
} from "../test/fixtures";
import {
  currentDecision,
  displayedNodeId,
  findEngagement,
  findNode,
  findTrack,
  interceptorCount,
  misalignment,
  missionCounts,
} from "./select";
import type { ScenarioState } from "./store";

const state = (overrides: Partial<ScenarioState> = {}): ScenarioState => ({
  snapshot: null,
  connection: "online",
  pending: null,
  error: null,
  interceptorRequests: {},
  selectedNodeId: null,
  location: "device",
  ...overrides,
});

describe("lookups", () => {
  const snapshot = makeDecisionSnapshot();

  it("find by id, or nothing", () => {
    expect(findNode(snapshot, "NODE-02")?.state).toBe("READY");
    expect(findTrack(snapshot, "T-002")?.site_distance_km).toBe(37.8);
    expect(findEngagement(snapshot, "R-02")?.node_id).toBe("NODE-03");
    expect(findNode(snapshot, "NODE-99")).toBeNull();
    expect(findTrack(snapshot, "T-099")).toBeNull();
    expect(findEngagement(snapshot, "R-99")).toBeNull();
  });

  it("presents the head of the backend's decision queue", () => {
    expect(currentDecision(snapshot)?.id).toBe("R-01");
    expect(currentDecision(makeSnapshot())).toBeNull();
  });
});

describe("missionCounts", () => {
  it("tallies what the mission bar shows", () => {
    expect(missionCounts(makeDecisionSnapshot())).toEqual({
      threats: 3,
      inbound: 3,
      inside: 2,
      pending: 2,
      inFlight: 0,
      intercepted: 0,
      reachedSite: 0,
    });
  });

  it("separates outcomes and interceptors in flight", () => {
    const snapshot = makeSnapshot({
      tracks: [
        makeTrack({ status: "INTERCEPTED" }),
        makeTrack({ id: "T-002", status: "REACHED_SITE" }),
        makeTrack({ id: "T-003" }),
      ],
      interceptors: [
        makeInterceptor(),
        makeInterceptor({ id: "INT-002", state: "STOOD_DOWN" }),
      ],
    });
    expect(missionCounts(snapshot)).toMatchObject({
      threats: 3,
      inbound: 1,
      intercepted: 1,
      reachedSite: 1,
      inFlight: 1,
    });
  });
});

describe("displayedNodeId", () => {
  it("follows the current decision by default", () => {
    expect(displayedNodeId(state({ snapshot: makeDecisionSnapshot() }))).toBe(
      "NODE-02",
    );
  });

  it("falls back to the first node when nothing is being decided", () => {
    expect(displayedNodeId(state({ snapshot: makeSnapshot() }))).toBe("NODE-01");
  });

  it("honours the operator's pick, ignoring one that no longer exists", () => {
    const snapshot = makeDecisionSnapshot();
    expect(displayedNodeId(state({ snapshot, selectedNodeId: "NODE-05" }))).toBe(
      "NODE-05",
    );
    expect(displayedNodeId(state({ snapshot, selectedNodeId: "NODE-99" }))).toBe(
      "NODE-02",
    );
  });

  it("has nothing to show without a snapshot", () => {
    expect(displayedNodeId(state())).toBeNull();
  });
});

describe("interceptorCount", () => {
  const engagement = makeEngagement({ proposed_interceptors: 2 });

  it("defaults to the proposal", () => {
    expect(interceptorCount(state(), engagement, makeNode())).toBe(2);
  });

  it("uses the operator's count, within the node's inventory", () => {
    const chosen = state({ interceptorRequests: { "R-01": 5 } });
    expect(interceptorCount(chosen, engagement, makeNode())).toBe(5);
    expect(interceptorCount(chosen, engagement, makeNode({ inventory: 3 }))).toBe(
      3,
    );
  });

  it("never drops below one, even with an empty node", () => {
    expect(interceptorCount(state(), engagement, makeNode({ inventory: 0 }))).toBe(
      1,
    );
  });
});

describe("misalignment", () => {
  it("is the worse of the two axes, the short way round", () => {
    expect(
      misalignment(
        makeNode({
          current_yaw_deg: 350,
          target_yaw_deg: 10,
          current_pitch_deg: 8,
          target_pitch_deg: 12,
        }),
      ),
    ).toBeCloseTo(20, 9);
    expect(
      misalignment(
        makeNode({
          current_yaw_deg: 72,
          target_yaw_deg: 72.2,
          current_pitch_deg: 0,
          target_pitch_deg: 12,
        }),
      ),
    ).toBeCloseTo(12, 9);
  });
});
