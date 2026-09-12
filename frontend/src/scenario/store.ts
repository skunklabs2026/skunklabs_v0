/**
 * The one mission state in the UI.
 *
 * The backend runs the defense scenario and publishes whole snapshots. This
 * store holds the latest one - the map, the launcher view, the 3D model and
 * the event log all read from here, so they cannot drift apart, and switching
 * views never resets or pauses anything. Nothing in the UI derives mission
 * state; it renders what arrives.
 *
 * Alongside the snapshot, a little client-side state that is the operator's
 * own and shared by both views: interceptor counts dialled in but not yet
 * authorized, which node the launcher view shows, and whether the device has
 * reported a location.
 *
 * Framework-free on purpose: React subscribes through `useSyncExternalStore`
 * (see hooks.ts), and the 3D render loop reads `getState()` every frame
 * without re-rendering anything.
 */

import type { ScenarioCommandName } from "../api/endpoints";
import type { ScenarioCommandResult, ScenarioSnapshot } from "./contract";

export type Connection = "connecting" | "online" | "offline";
export type Command = ScenarioCommandName;
export type LocationStatus = "locating" | "device" | "unavailable";

export interface CommandRequest {
  /** The response acted on, for authorize and decline. */
  engagementId?: string;
  body?: Record<string, unknown>;
  /**
   * Background command whose failure is expected and not shown - an automatic
   * location update while a mission is running, say. Never blocks the controls.
   */
  quiet?: boolean;
}

export interface ScenarioState {
  snapshot: ScenarioSnapshot | null;
  connection: Connection;
  /** The operator command awaiting a response, if any. Controls disable meanwhile. */
  pending: Command | null;
  /** The backend's explanation of the last rejected command. */
  error: string | null;
  /** Interceptors dialled in per response, where the operator changed the proposal. */
  interceptorRequests: Record<string, number>;
  /** The node the launcher view shows; null follows the current decision. */
  selectedNodeId: string | null;
  location: LocationStatus;
}

/** The subset of WebSocket the store uses - lets tests supply a fake. */
export interface SocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  close(): void;
}

export interface ScenarioTransport {
  openSocket(): SocketLike;
  send(
    command: Command,
    request: Pick<CommandRequest, "engagementId" | "body">,
  ): Promise<ScenarioCommandResult>;
}

export interface ScenarioStore {
  getState(): ScenarioState;
  subscribe(listener: () => void): () => void;
  /** Open the live feed. Returns a disposer; reconnects until disposed. */
  connect(): () => void;
  /** Resolves true when the backend accepted the command. */
  command(command: Command, request?: CommandRequest): Promise<boolean>;
  setInterceptorRequest(engagementId: string, count: number): void;
  selectNode(nodeId: string | null): void;
  setLocation(status: LocationStatus): void;
}

const INITIAL: ScenarioState = {
  snapshot: null,
  connection: "connecting",
  pending: null,
  error: null,
  interceptorRequests: {},
  selectedNodeId: null,
  location: "locating",
};

export function parseSnapshot(data: unknown): ScenarioSnapshot | null {
  if (typeof data !== "string") return null;
  try {
    const message = JSON.parse(data) as { type?: unknown };
    return message.type === "scenario" ? (message as ScenarioSnapshot) : null;
  } catch {
    return null;
  }
}

export function createScenarioStore(
  transport: ScenarioTransport,
  { reconnectMs = 1200 }: { reconnectMs?: number } = {},
): ScenarioStore {
  let state = INITIAL;
  const listeners = new Set<() => void>();

  const set = (patch: Partial<ScenarioState>) => {
    state = { ...state, ...patch };
    listeners.forEach((listener) => listener());
  };

  // A backend restart resets its revision counter, so the first snapshot on
  // a fresh connection is always accepted.
  let acceptAnyRevision = true;

  const apply = (snapshot: ScenarioSnapshot) => {
    const current = state.snapshot;
    if (!acceptAnyRevision && current && snapshot.revision < current.revision) {
      return; // An older copy that lost the race to a newer one.
    }
    acceptAnyRevision = false;
    set({ snapshot });
  };

  const connect = () => {
    // Per-call closures, so a superseded connection (React StrictMode mounts
    // effects twice) can never act on its successor.
    let disposed = false;
    let socket: SocketLike | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const open = () => {
      if (disposed) return;
      const current = transport.openSocket();
      socket = current;

      current.onopen = () => {
        if (disposed || socket !== current) return;
        acceptAnyRevision = true;
        set({ connection: "online" });
      };
      current.onmessage = (event) => {
        if (disposed || socket !== current) return;
        const snapshot = parseSnapshot(event.data);
        if (snapshot) apply(snapshot);
      };
      current.onclose = () => {
        if (disposed || socket !== current) return;
        socket = null;
        set({ connection: "offline" });
        timer = setTimeout(open, reconnectMs);
      };
      current.onerror = () => current.close();
    };

    open();
    return () => {
      disposed = true;
      if (timer !== null) clearTimeout(timer);
      socket?.close();
      socket = null;
    };
  };

  const command = async (
    name: Command,
    { engagementId, body, quiet = false }: CommandRequest = {},
  ) => {
    if (quiet) {
      try {
        apply((await transport.send(name, { engagementId, body })).snapshot);
        return true;
      } catch {
        return false;
      }
    }

    if (state.pending) return false;
    set({ pending: name, error: null });
    try {
      const result = await transport.send(name, { engagementId, body });
      apply(result.snapshot);
      // A reset clears the operator's unsent choices too.
      set(
        name === "reset"
          ? { pending: null, interceptorRequests: {}, selectedNodeId: null }
          : { pending: null },
      );
      return true;
    } catch (error) {
      set({
        pending: null,
        error: error instanceof Error ? error.message : "Command failed",
      });
      return false;
    }
  };

  return {
    getState: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    connect,
    command,
    setInterceptorRequest: (engagementId, count) =>
      set({
        interceptorRequests: {
          ...state.interceptorRequests,
          [engagementId]: Math.max(1, Math.round(count)),
        },
      }),
    selectNode: (nodeId) => set({ selectedNodeId: nodeId }),
    setLocation: (location) => set({ location }),
  };
}
