import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeSnapshot } from "../test/fixtures";
import type { ScenarioCommandResult } from "./contract";
import {
  createScenarioStore,
  parseSnapshot,
  type Command,
  type CommandRequest,
  type SocketLike,
} from "./store";

class FakeSocket implements SocketLike {
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  close() {
    this.closed = true;
    this.onclose?.(new CloseEvent("close"));
  }

  open() {
    this.onopen?.(new Event("open"));
  }

  error() {
    this.onerror?.(new Event("error"));
  }

  receive(data: unknown) {
    this.onmessage?.(
      new MessageEvent("message", {
        data: typeof data === "string" ? data : JSON.stringify(data),
      }),
    );
  }
}

type Send = (
  command: Command,
  request: Pick<CommandRequest, "engagementId" | "body">,
) => Promise<ScenarioCommandResult>;

function setup() {
  const sockets: FakeSocket[] = [];
  const send = vi.fn<Send>();
  const store = createScenarioStore(
    {
      openSocket: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
      send,
    },
    { reconnectMs: 1000 },
  );
  return { store, sockets, send };
}

const ok = (snapshot = makeSnapshot()): ScenarioCommandResult => ({
  ok: true,
  detail: "",
  snapshot,
});

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("parseSnapshot", () => {
  it("accepts scenario messages only", () => {
    expect(parseSnapshot(JSON.stringify(makeSnapshot()))?.type).toBe("scenario");
    expect(parseSnapshot(JSON.stringify({ type: "telemetry" }))).toBeNull();
    expect(parseSnapshot("{not json")).toBeNull();
    expect(parseSnapshot(42)).toBeNull();
  });
});

describe("scenario store - live feed", () => {
  it("starts connecting, with nothing chosen yet", () => {
    const { store } = setup();
    expect(store.getState()).toEqual({
      snapshot: null,
      connection: "connecting",
      pending: null,
      error: null,
      interceptorRequests: {},
      selectedNodeId: null,
      location: "locating",
    });
  });

  it("goes online and publishes each snapshot to subscribers", () => {
    const { store, sockets } = setup();
    const listener = vi.fn();
    store.subscribe(listener);
    store.connect();

    sockets[0].open();
    expect(store.getState().connection).toBe("online");

    const snapshot = makeSnapshot({ revision: 3, running: true });
    sockets[0].receive(snapshot);
    expect(store.getState().snapshot).toEqual(snapshot);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("stops notifying an unsubscribed listener", () => {
    const { store, sockets } = setup();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    unsubscribe();
    store.connect();
    sockets[0].open();
    expect(listener).not.toHaveBeenCalled();
  });

  it("ignores messages that are not scenario snapshots", () => {
    const { store, sockets } = setup();
    store.connect();
    sockets[0].open();
    sockets[0].receive("garbage");
    sockets[0].receive({ type: "history" });
    expect(store.getState().snapshot).toBeNull();
  });

  it("keeps the newest revision when copies arrive out of order", () => {
    const { store, sockets } = setup();
    store.connect();
    sockets[0].open();
    sockets[0].receive(makeSnapshot({ revision: 5, elapsed_s: 5 }));
    sockets[0].receive(makeSnapshot({ revision: 3, elapsed_s: 3 }));
    expect(store.getState().snapshot?.revision).toBe(5);
  });

  it("reconnects after a drop and accepts a restarted backend's lower revision", () => {
    const { store, sockets } = setup();
    store.connect();
    sockets[0].open();
    sockets[0].receive(makeSnapshot({ revision: 40 }));

    sockets[0].close();
    expect(store.getState().connection).toBe("offline");
    expect(sockets).toHaveLength(1);

    vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(2);
    sockets[1].open();
    sockets[1].receive(makeSnapshot({ revision: 1 }));
    expect(store.getState().connection).toBe("online");
    expect(store.getState().snapshot?.revision).toBe(1);
  });

  it("closes on socket error", () => {
    const { store, sockets } = setup();
    store.connect();
    sockets[0].error();
    expect(sockets[0].closed).toBe(true);
    expect(store.getState().connection).toBe("offline");
  });

  it("disposing closes the socket and stops reconnecting", () => {
    const { store, sockets } = setup();
    const dispose = store.connect();
    sockets[0].open();
    dispose();
    expect(sockets[0].closed).toBe(true);

    vi.advanceTimersByTime(5000);
    expect(sockets).toHaveLength(1);
    // Late events from the disposed connection change nothing.
    sockets[0].receive(makeSnapshot({ revision: 9 }));
    sockets[0].open();
    expect(store.getState().snapshot).toBeNull();
  });

  it("cancels a pending reconnect on dispose", () => {
    const { store, sockets } = setup();
    const dispose = store.connect();
    sockets[0].close();
    dispose();
    vi.advanceTimersByTime(5000);
    expect(sockets).toHaveLength(1);
  });
});

describe("scenario store - commands", () => {
  it("marks the command pending, then applies the returned snapshot", async () => {
    const { store, send } = setup();
    const snapshot = makeSnapshot({ revision: 2, running: true, can_start: false });
    let resolve!: (result: ScenarioCommandResult) => void;
    send.mockReturnValue(new Promise((r) => (resolve = r)));

    const done = store.command("start");
    expect(send).toHaveBeenCalledWith("start", {
      engagementId: undefined,
      body: undefined,
    });
    expect(store.getState().pending).toBe("start");

    resolve(ok(snapshot));
    await expect(done).resolves.toBe(true);
    expect(store.getState().pending).toBeNull();
    expect(store.getState().snapshot).toEqual(snapshot);
  });

  it("addresses one response when authorizing or declining", async () => {
    const { store, send } = setup();
    send.mockResolvedValue(ok());
    await store.command("authorize", {
      engagementId: "R-02",
      body: { interceptors: 3 },
    });
    expect(send).toHaveBeenCalledWith("authorize", {
      engagementId: "R-02",
      body: { interceptors: 3 },
    });
    await store.command("decline", { engagementId: "R-03" });
    expect(send).toHaveBeenLastCalledWith("decline", {
      engagementId: "R-03",
      body: undefined,
    });
  });

  it("refuses a second command while one is pending", async () => {
    const { store, send } = setup();
    send.mockReturnValue(new Promise(() => {}));
    void store.command("start");
    await expect(store.command("reset")).resolves.toBe(false);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("keeps the backend's explanation of a rejection", async () => {
    const { store, send } = setup();
    send.mockRejectedValue(new Error("Authorization rejected - R-01 is PROPOSED"));
    await expect(
      store.command("authorize", { engagementId: "R-01" }),
    ).resolves.toBe(false);
    expect(store.getState()).toMatchObject({
      pending: null,
      error: "Authorization rejected - R-01 is PROPOSED",
    });
  });

  it("clears the previous error on the next command", async () => {
    const { store, send } = setup();
    send.mockRejectedValueOnce("boom");
    await store.command("start");
    expect(store.getState().error).toBe("Command failed");

    send.mockResolvedValueOnce(ok());
    await store.command("start");
    expect(store.getState().error).toBeNull();
  });

  it("runs a quiet command without blocking or reporting", async () => {
    const { store, send } = setup();
    const snapshot = makeSnapshot({ revision: 4 });
    send.mockResolvedValueOnce(ok(snapshot));
    await expect(
      store.command("configure", {
        body: { latitude: 1, longitude: 2 },
        quiet: true,
      }),
    ).resolves.toBe(true);
    expect(store.getState()).toMatchObject({
      snapshot,
      pending: null,
      error: null,
    });

    send.mockRejectedValueOnce(new Error("Reset the demo first."));
    await expect(
      store.command("configure", {
        body: { latitude: 1, longitude: 2 },
        quiet: true,
      }),
    ).resolves.toBe(false);
    expect(store.getState().error).toBeNull();
  });
});

describe("scenario store - operator choices", () => {
  it("holds a whole number of at least one interceptor per response", () => {
    const { store } = setup();
    store.setInterceptorRequest("R-01", 3);
    store.setInterceptorRequest("R-02", 0);
    store.setInterceptorRequest("R-03", 2.4);
    expect(store.getState().interceptorRequests).toEqual({
      "R-01": 3,
      "R-02": 1,
      "R-03": 2,
    });
  });

  it("remembers which node the launcher view shows", () => {
    const { store } = setup();
    store.selectNode("NODE-04");
    expect(store.getState().selectedNodeId).toBe("NODE-04");
    store.selectNode(null);
    expect(store.getState().selectedNodeId).toBeNull();
  });

  it("records what the device said about location", () => {
    const { store } = setup();
    store.setLocation("unavailable");
    expect(store.getState().location).toBe("unavailable");
  });

  it("clears the operator's unsent choices on reset only", async () => {
    const { store, send } = setup();
    send.mockResolvedValue(ok());
    store.setInterceptorRequest("R-01", 3);
    store.selectNode("NODE-05");

    await store.command("start");
    expect(store.getState()).toMatchObject({
      interceptorRequests: { "R-01": 3 },
      selectedNodeId: "NODE-05",
    });

    await store.command("reset");
    expect(store.getState()).toMatchObject({
      interceptorRequests: {},
      selectedNodeId: null,
    });
  });
});
