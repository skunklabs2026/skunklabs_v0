import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { authorize, reset, fetchTelemetry, fetchEvents } from "./mission";

const fetchMock = vi.fn();

function ok(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response;
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(ok({}));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mission commands", () => {
  it("POSTs authorize — the one operator action that arms actuation", async () => {
    await authorize();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/authorize",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("POSTs reset", async () => {
    await reset();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reset",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("GETs the telemetry snapshot", async () => {
    fetchMock.mockResolvedValue(ok({ state: "TRACKING" }));
    await expect(fetchTelemetry()).resolves.toEqual({ state: "TRACKING" });
    expect(fetchMock).toHaveBeenCalledWith("/api/telemetry", undefined);
  });

  it("GETs the event log", async () => {
    fetchMock.mockResolvedValue(ok([{ state: "SEARCHING" }]));
    await expect(fetchEvents()).resolves.toEqual([{ state: "SEARCHING" }]);
    expect(fetchMock).toHaveBeenCalledWith("/api/events", undefined);
  });
});
