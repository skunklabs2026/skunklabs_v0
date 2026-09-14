import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "./App";
import { expectRenderErrors } from "./test/helpers";
import { makeTelemetry, makeSystem, makeSourceStatus } from "./test/factories";

// These suites throw during render on purpose.
expectRenderErrors();

const telemetryState = vi.hoisted(() => ({
  telemetry: null as unknown,
  events: [] as unknown[],
  connected: true,
  authorize: vi.fn(),
  reset: vi.fn(),
}));

vi.mock("./hooks/useTelemetry", () => ({
  useTelemetry: () => telemetryState,
}));

const api = vi.hoisted(() => ({
  fetchStatus: vi.fn(),
  selectVideo: vi.fn(),
  selectDetector: vi.fn(),
  setThreshold: vi.fn(),
  selectCamera: vi.fn(),
  removeUpload: vi.fn(),
  uploadVideo: vi.fn(),
}));

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, sourceApi: api };
});

const live = makeTelemetry({
  system: makeSystem({ sensor_online: true, frame_index: 120 }),
});

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset?.());
  api.fetchStatus.mockResolvedValue(makeSourceStatus());
  telemetryState.telemetry = live;
  telemetryState.events = [];
  telemetryState.connected = true;
  telemetryState.authorize.mockReset().mockResolvedValue({ ok: true });
  telemetryState.reset.mockReset().mockResolvedValue({ ok: true });
});

async function start() {
  const result = render(<App />);
  await waitFor(() => expect(api.fetchStatus).toHaveBeenCalled());
  return result;
}

describe("App", () => {
  // Nothing runs on the console until the operator has chosen and verified a
  // source.
  it("opens on Mission Setup, not the console", async () => {
    await start();
    expect(screen.getByText("Canister 01 · Mission Setup")).toBeInTheDocument();
    expect(screen.queryByText("Event Log")).not.toBeInTheDocument();
  });

  it("moves to the console when the operator begins", async () => {
    await start();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Begin mission" }));
    });
    expect(screen.getByText("Event Log")).toBeInTheDocument();
    expect(
      screen.queryByText("Canister 01 · Mission Setup"),
    ).not.toBeInTheDocument();
  });

  // A fresh sequence, not whatever accumulated during setup.
  it("resets the mission on the way in", async () => {
    await start();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Begin mission" }));
    });
    expect(telemetryState.reset).toHaveBeenCalledTimes(1);
  });

  it("returns to setup from the console", async () => {
    await start();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Begin mission" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Change Source" }));
    });
    expect(screen.getByText("Canister 01 · Mission Setup")).toBeInTheDocument();
  });

  it("wires the console's authorize control through to the backend", async () => {
    telemetryState.telemetry = makeTelemetry({
      system: makeSystem({ sensor_online: true, frame_index: 120 }),
      mission: { ...makeTelemetry().mission, can_authorize: true },
    });
    await start();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Begin mission" }));
    });
    fireEvent.click(screen.getByRole("button", { name: "Authorize" }));
    expect(telemetryState.authorize).toHaveBeenCalled();
  });

  it("wires the console's reset control through to the backend", async () => {
    await start();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Begin mission" }));
    });
    telemetryState.reset.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Reset Mission" }));
    expect(telemetryState.reset).toHaveBeenCalled();
  });

  // One socket for the whole app: switching screens must not drop it.
  it("subscribes to telemetry once, above both screens", async () => {
    await start();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Begin mission" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Change Source" }));
    });
    // Telemetry is still flowing on the setup screen after the round trip.
    expect(screen.getByText("Backend online")).toBeInTheDocument();
  });

  // The boundary is the difference between one bad panel and a white screen
  // mid-demo. It has to catch failures above the per-panel boundaries too.
  it("wraps the whole console in an error boundary", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    telemetryState.telemetry = makeTelemetry({
      system: makeSystem({ sensor_online: true, frame_index: 120 }),
      // Malformed targets break OperatorScreen's own memo, above every
      // per-panel boundary — only the App-level one can catch this.
      targets: "not an array" as never,
    });
    await start();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Begin mission" }));
    });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Console unavailable")).toBeInTheDocument();
    consoleError.mockRestore();
  });
});
