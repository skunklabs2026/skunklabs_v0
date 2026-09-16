import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useTelemetry } from "./useTelemetry";
import type { MissionEvent, TelemetryFrame } from "../types";

/** A WebSocket stand-in that a test can open, message and close by hand. */
class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  close() {
    this.closed = true;
    this.onclose?.();
  }
  /** Deliver a frame as the server would. */
  send(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
  sendRaw(data: string) {
    this.onmessage?.({ data } as MessageEvent);
  }
  static get latest() {
    return FakeSocket.instances[FakeSocket.instances.length - 1];
  }
}

const authorize = vi.fn();
const reset = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    missionApi: {
      authorize: () => authorize(),
      reset: () => reset(),
      fetchTelemetry: vi.fn(),
      fetchEvents: vi.fn(),
    },
  };
});

function frame(overrides: Partial<TelemetryFrame> = {}): TelemetryFrame {
  return { events: [], ...overrides } as TelemetryFrame;
}

function event(message: string): MissionEvent {
  return { timestamp: 1_700_000_000, kind: "info", message };
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.useFakeTimers();
  authorize.mockReset().mockResolvedValue({ ok: true });
  reset.mockReset().mockResolvedValue({ ok: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("connection", () => {
  it("opens the telemetry socket and reports connected on open", () => {
    const { result } = renderHook(() => useTelemetry());
    expect(FakeSocket.latest.url).toMatch(/\/ws\/telemetry$/);
    expect(result.current.connected).toBe(false);

    act(() => FakeSocket.latest.onopen?.());
    expect(result.current.connected).toBe(true);
  });

  it("reconnects after a drop — the operator never reloads mid-demo", () => {
    const { result } = renderHook(() => useTelemetry());
    act(() => FakeSocket.latest.onopen?.());
    expect(FakeSocket.instances).toHaveLength(1);

    act(() => FakeSocket.latest.close());
    expect(result.current.connected).toBe(false);

    act(() => void vi.advanceTimersByTime(1199));
    expect(FakeSocket.instances).toHaveLength(1);
    act(() => void vi.advanceTimersByTime(1));
    expect(FakeSocket.instances).toHaveLength(2);

    act(() => FakeSocket.latest.onopen?.());
    expect(result.current.connected).toBe(true);
  });

  it("an error closes the socket, which triggers the reconnect path", () => {
    renderHook(() => useTelemetry());
    const first = FakeSocket.latest;
    act(() => first.onerror?.());
    expect(first.closed).toBe(true);

    act(() => void vi.advanceTimersByTime(1200));
    expect(FakeSocket.instances).toHaveLength(2);
  });

  it("closes the socket and cancels the reconnect on unmount", () => {
    const { unmount } = renderHook(() => useTelemetry());
    const socket = FakeSocket.latest;

    unmount();
    expect(socket.closed).toBe(true);

    act(() => void vi.advanceTimersByTime(5000));
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("ignores frames that arrive after disposal", () => {
    const { result, unmount } = renderHook(() => useTelemetry());
    const socket = FakeSocket.latest;
    unmount();

    act(() => socket.send(frame({ events: [event("late")] })));
    expect(result.current.telemetry).toBeNull();
  });
});

describe("messages", () => {
  it("replaces the log from a history message", () => {
    const { result } = renderHook(() => useTelemetry());
    act(() =>
      FakeSocket.latest.send({ type: "history", events: [event("a"), event("b")] }),
    );
    expect(result.current.events).toHaveLength(2);
    expect(result.current.telemetry).toBeNull();
  });

  it("keeps only the most recent 200 history entries", () => {
    const { result } = renderHook(() => useTelemetry());
    const many = Array.from({ length: 250 }, (_, i) => event(`e${i}`));
    act(() => FakeSocket.latest.send({ type: "history", events: many }));

    expect(result.current.events).toHaveLength(200);
    expect(result.current.events[0]).toEqual(event("e50"));
  });

  it("stores a telemetry frame and appends its events", () => {
    const { result } = renderHook(() => useTelemetry());
    act(() => FakeSocket.latest.send(frame({ events: [event("one")] })));
    act(() => FakeSocket.latest.send(frame({ events: [event("two")] })));

    expect(result.current.telemetry).not.toBeNull();
    expect(result.current.events.map((e) => e.message)).toEqual(["one", "two"]);
  });

  it("caps the appended log at 200", () => {
    const { result } = renderHook(() => useTelemetry());
    for (let i = 0; i < 205; i++) {
      act(() => FakeSocket.latest.send(frame({ events: [event(`e${i}`)] })));
    }
    expect(result.current.events).toHaveLength(200);
    expect(result.current.events[199]).toEqual(event("e204"));
  });

  it("a frame with no events leaves the log alone", () => {
    const { result } = renderHook(() => useTelemetry());
    act(() => FakeSocket.latest.send(frame({ events: [event("kept")] })));
    act(() => FakeSocket.latest.send(frame({ events: [] })));
    expect(result.current.events).toHaveLength(1);
  });

  it("ignores malformed JSON rather than throwing", () => {
    const { result } = renderHook(() => useTelemetry());
    act(() => FakeSocket.latest.sendRaw("{not json"));
    expect(result.current.telemetry).toBeNull();
    expect(result.current.events).toEqual([]);
  });
});

// These resolve to null rather than throwing: the mission state that matters
// arrives on the next frame regardless, and rejecting here would only surface
// as an unhandled rejection.
describe("commands", () => {
  beforeEach(() => vi.useRealTimers());

  it("authorize returns the response", async () => {
    const { result } = renderHook(() => useTelemetry());
    await expect(result.current.authorize()).resolves.toEqual({ ok: true });
  });

  it("authorize resolves to null when the request fails", async () => {
    authorize.mockRejectedValue(new Error("refused"));
    const { result } = renderHook(() => useTelemetry());
    await expect(result.current.authorize()).resolves.toBeNull();
  });

  it("reset returns the response", async () => {
    const { result } = renderHook(() => useTelemetry());
    await expect(result.current.reset()).resolves.toEqual({ ok: true });
  });

  it("reset resolves to null when the request fails", async () => {
    reset.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useTelemetry());
    await expect(result.current.reset()).resolves.toBeNull();
  });

  it("keeps a stable identity so consumers can depend on it", async () => {
    const { result, rerender } = renderHook(() => useTelemetry());
    const first = result.current.authorize;
    rerender();
    await waitFor(() => expect(result.current.authorize).toBe(first));
  });
});
