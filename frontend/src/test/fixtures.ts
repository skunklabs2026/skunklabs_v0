/** Scenario test data and a store the test controls. */

import { act } from "@testing-library/react";
import { vi } from "vitest";
import type {
  DefenseNode,
  Engagement,
  ScenarioSnapshot,
  SimulatedInterceptor,
  Track,
} from "../scenario/contract";
import type {
  Command,
  CommandRequest,
  LocationStatus,
  ScenarioState,
  ScenarioStore,
} from "../scenario/store";

const NODE_POSITIONS: [number, number][] = [
  [50.173, 36.23],
  [50.083, 36.477],
  [49.903, 36.477],
  [49.813, 36.23],
  [49.903, 35.983],
  [50.083, 35.983],
];

export function makeNode(overrides: Partial<DefenseNode> = {}): DefenseNode {
  return {
    id: "NODE-01",
    latitude: 50.173,
    longitude: 36.23,
    coverage_radius_km: 25,
    current_yaw_deg: 0,
    target_yaw_deg: 0,
    current_pitch_deg: 0,
    target_pitch_deg: 0,
    state: "STANDBY",
    engagement_id: null,
    inventory: 6,
    inventory_capacity: 6,
    ...overrides,
  };
}

/** Six standby nodes on the ring, each facing outward. */
export function makeNodes(): DefenseNode[] {
  return NODE_POSITIONS.map(([latitude, longitude], index) =>
    makeNode({
      id: `NODE-0${index + 1}`,
      latitude,
      longitude,
      current_yaw_deg: index * 60,
      target_yaw_deg: index * 60,
    }),
  );
}

export function withNode(
  nodes: DefenseNode[],
  id: string,
  patch: Partial<DefenseNode>,
): DefenseNode[] {
  return nodes.map((node) => (node.id === id ? { ...node, ...patch } : node));
}

export function makeSnapshot(
  overrides: Partial<ScenarioSnapshot> = {},
): ScenarioSnapshot {
  return {
    type: "scenario",
    revision: 1,
    state: "IDLE",
    scenario_id: "S1",
    scenarios: [
      {
        id: "S1",
        name: "Scenario 1",
        description: "4 drones approaching from the east",
        threat_count: 4,
      },
      {
        id: "S2",
        name: "Scenario 2",
        description: "3 drones from the east, 3 from the west",
        threat_count: 6,
      },
      {
        id: "S3",
        name: "Scenario 3",
        description: "4 drones from the north, 2 from the southeast",
        threat_count: 6,
      },
    ],
    running: false,
    elapsed_s: 0,
    time_scale: 20,
    site: {
      id: "SITE-A",
      name: "Protected infrastructure",
      latitude: 49.993,
      longitude: 36.23,
      protected_radius_km: 40,
      location_source: "DEVICE",
    },
    nodes: makeNodes(),
    tracks: [],
    engagements: [],
    interceptors: [],
    decision_queue: [],
    can_start: true,
    can_configure: true,
    fault: null,
    events: [],
    ...overrides,
  };
}

export function makeTrack(overrides: Partial<Track> = {}): Track {
  return {
    id: "T-001",
    latitude: 50.05,
    longitude: 36.75,
    altitude_m: 1000,
    heading_deg: 265,
    speed_kmh: 180,
    status: "INBOUND",
    source: "SIMULATED",
    site_distance_km: 37.62,
    inside_protected_area: true,
    engagement_id: null,
    trail: [
      { latitude: 50.06, longitude: 36.85 },
      { latitude: 50.05, longitude: 36.75 },
    ],
    ...overrides,
  };
}

export function makeEngagement(overrides: Partial<Engagement> = {}): Engagement {
  return {
    id: "R-01",
    node_id: "NODE-02",
    track_id: "T-001",
    status: "AWAITING_AUTHORIZATION",
    proposed_interceptors: 2,
    range_km: 21.94,
    bearing_deg: 81.3,
    elevation_deg: 2.61,
    interceptor_ids: [],
    intercept_point: null,
    ...overrides,
  };
}

export function makeInterceptor(
  overrides: Partial<SimulatedInterceptor> = {},
): SimulatedInterceptor {
  return {
    id: "INT-001",
    node_id: "NODE-02",
    track_id: "T-001",
    engagement_id: "R-01",
    latitude: 50.07,
    longitude: 36.6,
    heading_deg: 80,
    state: "IN_FLIGHT",
    trail: [
      { latitude: 50.083, longitude: 36.477 },
      { latitude: 50.07, longitude: 36.6 },
    ],
    ...overrides,
  };
}

/**
 * A running mission: R-01 (NODE-02 → T-001) awaits a decision, R-02
 * (NODE-03 → T-002) is still orienting, T-003 is outside the protected area.
 */
export function makeDecisionSnapshot(
  overrides: Partial<ScenarioSnapshot> = {},
): ScenarioSnapshot {
  let nodes = withNode(makeNodes(), "NODE-02", {
    state: "READY",
    engagement_id: "R-01",
    current_yaw_deg: 81.3,
    target_yaw_deg: 81.3,
    current_pitch_deg: 12,
    target_pitch_deg: 12,
  });
  nodes = withNode(nodes, "NODE-03", {
    state: "ORIENTING",
    engagement_id: "R-02",
    current_yaw_deg: 110,
    target_yaw_deg: 98.5,
    current_pitch_deg: 8,
    target_pitch_deg: 12,
  });
  return makeSnapshot({
    state: "RUNNING",
    running: true,
    can_start: false,
    can_configure: false,
    elapsed_s: 9.2,
    nodes,
    tracks: [
      makeTrack({ engagement_id: "R-01" }),
      makeTrack({ id: "T-002", site_distance_km: 37.8, engagement_id: "R-02" }),
      makeTrack({
        id: "T-003",
        site_distance_km: 41.2,
        inside_protected_area: false,
      }),
    ],
    engagements: [
      makeEngagement(),
      makeEngagement({
        id: "R-02",
        node_id: "NODE-03",
        track_id: "T-002",
        status: "PROPOSED",
        bearing_deg: 98.5,
      }),
    ],
    decision_queue: ["R-01", "R-02"],
    ...overrides,
  });
}

/** A store whose state the test sets directly, with spied commands. */
export function fakeStore(initial: Partial<ScenarioState> = {}) {
  let state: ScenarioState = {
    snapshot: null,
    connection: "online",
    pending: null,
    error: null,
    interceptorRequests: {},
    selectedNodeId: null,
    location: "device",
    ...initial,
  };
  const listeners = new Set<() => void>();
  const set = (patch: Partial<ScenarioState>) =>
    act(() => {
      state = { ...state, ...patch };
      listeners.forEach((listener) => listener());
    });
  const command = vi.fn(
    async (_command: Command, _request?: CommandRequest): Promise<boolean> => true,
  );
  const setInterceptorRequest = vi.fn((engagementId: string, count: number) =>
    set({
      interceptorRequests: { ...state.interceptorRequests, [engagementId]: count },
    }),
  );
  const selectNode = vi.fn((nodeId: string | null) =>
    set({ selectedNodeId: nodeId }),
  );
  const setLocation = vi.fn((location: LocationStatus) => set({ location }));
  const store: ScenarioStore = {
    getState: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    connect: vi.fn(() => () => {}),
    command,
    setInterceptorRequest,
    selectNode,
    setLocation,
  };
  return { store, set, command, setInterceptorRequest, selectNode, setLocation };
}
