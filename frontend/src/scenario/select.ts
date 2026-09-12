/**
 * Lookups and tallies over a snapshot, for display.
 *
 * Nothing here decides anything: which responses await a decision, what is
 * authorizable and what state each node is in all arrive from the backend.
 * These only find things and count them.
 */

import type { DefenseNode, Engagement, ScenarioSnapshot, Track } from "./contract";
import { shortestDelta } from "./geo";
import type { ScenarioState } from "./store";

export function findNode(
  snapshot: ScenarioSnapshot,
  id: string,
): DefenseNode | null {
  return snapshot.nodes.find((node) => node.id === id) ?? null;
}

export function findTrack(snapshot: ScenarioSnapshot, id: string): Track | null {
  return snapshot.tracks.find((track) => track.id === id) ?? null;
}

export function findEngagement(
  snapshot: ScenarioSnapshot,
  id: string,
): Engagement | null {
  return snapshot.engagements.find((engagement) => engagement.id === id) ?? null;
}

/** The response presented to the operator now: the head of the backend's queue. */
export function currentDecision(snapshot: ScenarioSnapshot): Engagement | null {
  const id = snapshot.decision_queue[0];
  return id ? findEngagement(snapshot, id) : null;
}

export interface MissionCounts {
  threats: number;
  inbound: number;
  inside: number;
  pending: number;
  inFlight: number;
  intercepted: number;
  reachedSite: number;
}

export function missionCounts(snapshot: ScenarioSnapshot): MissionCounts {
  const { tracks } = snapshot;
  return {
    threats: tracks.length,
    inbound: tracks.filter((t) => t.status === "INBOUND").length,
    inside: tracks.filter((t) => t.status === "INBOUND" && t.inside_protected_area)
      .length,
    pending: snapshot.decision_queue.length,
    inFlight: snapshot.interceptors.filter((i) => i.state === "IN_FLIGHT").length,
    intercepted: tracks.filter((t) => t.status === "INTERCEPTED").length,
    reachedSite: tracks.filter((t) => t.status === "REACHED_SITE").length,
  };
}

/** The node the launcher view shows: the operator's pick, else the current decision's. */
export function displayedNodeId(state: ScenarioState): string | null {
  const { snapshot, selectedNodeId } = state;
  if (!snapshot) return null;
  if (selectedNodeId && findNode(snapshot, selectedNodeId)) return selectedNodeId;
  return currentDecision(snapshot)?.node_id ?? snapshot.nodes[0]?.id ?? null;
}

/** Interceptors for a response: the operator's count, else the proposal, within inventory. */
export function interceptorCount(
  state: ScenarioState,
  engagement: Engagement,
  node: DefenseNode,
): number {
  const requested =
    state.interceptorRequests[engagement.id] ?? engagement.proposed_interceptors;
  return Math.min(Math.max(requested, 1), Math.max(node.inventory, 1));
}

/** How far a node still has to turn, degrees, on its worse axis. */
export function misalignment(node: DefenseNode): number {
  return Math.max(
    Math.abs(shortestDelta(node.current_yaw_deg, node.target_yaw_deg)),
    Math.abs(node.target_pitch_deg - node.current_pitch_deg),
  );
}
