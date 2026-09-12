import { useCallback, useEffect, useState } from "react";
import { endpoints, missionApi } from "../api";
import type {
  CommandResponse,
  MissionEvent,
  ServerMessage,
  TelemetryFrame,
} from "../types";

const MAX_EVENTS = 200;
const RECONNECT_DELAY_MS = 1200;

export interface Telemetry {
  telemetry: TelemetryFrame | null;
  events: MissionEvent[];
  connected: boolean;
  authorize: () => Promise<CommandResponse | null>;
  reset: () => Promise<CommandResponse | null>;
}

/**
 * Subscribes to backend telemetry.
 *
 * The backend is the authoritative source of mission state - this hook only
 * transports it. It never derives, infers or smooths mission state, because
 * a UI that disagrees with the backend is worse than a UI that briefly shows
 * a stale frame.
 *
 * Reconnects automatically: an operator must never have to reload the page
 * mid-demo because the backend restarted.
 */
export function useTelemetry(): Telemetry {
  const [telemetry, setTelemetry] = useState<TelemetryFrame | null>(null);
  const [events, setEvents] = useState<MissionEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    // `disposed` and `socket` are local to this effect run, not refs shared
    // across runs. That distinction matters: React StrictMode mounts effects
    // twice, and with shared state the first run's close handler fires after
    // the second run has already reconnected, sees a cleared flag, and opens
    // a third socket. Two live sockets then both append to the event log,
    // producing duplicated and out-of-order entries. Per-run closures make
    // each connection's handlers only ever act on their own connection.
    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;

    const handle = (raw: MessageEvent) => {
      if (disposed) return;

      let message: ServerMessage;
      try {
        message = JSON.parse(raw.data as string);
      } catch {
        return;
      }

      if (message.type === "history") {
        // Sent once on connect, so a page opened mid-run - or reopened
        // after a drop - shows the whole event log, not just what follows.
        setEvents(message.events.slice(-MAX_EVENTS));
        return;
      }

      setTelemetry(message);
      if (message.events.length > 0) {
        setEvents((previous) =>
          [...previous, ...message.events].slice(-MAX_EVENTS),
        );
      }
    };

    const connect = () => {
      if (disposed) return;

      socket = new WebSocket(endpoints.telemetrySocket());
      const thisSocket = socket;

      socket.onopen = () => {
        if (!disposed) setConnected(true);
      };

      socket.onmessage = handle;

      socket.onclose = () => {
        // Ignore a close from a superseded connection.
        if (disposed || thisSocket !== socket) return;
        setConnected(false);
        socket = null;
        reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
      };

      socket.onerror = () => thisSocket.close();
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
      socket = null;
    };
  }, []);

  // Commands resolve to null rather than throwing: the mission state that
  // matters arrives on the next telemetry frame regardless, and a rejected
  // promise here would only surface as an unhandled rejection.
  const authorize = useCallback(async () => {
    try {
      return await missionApi.authorize();
    } catch {
      return null;
    }
  }, []);

  const reset = useCallback(async () => {
    try {
      return await missionApi.reset();
    } catch {
      return null;
    }
  }, []);

  return { telemetry, events, connected, authorize, reset };
}
