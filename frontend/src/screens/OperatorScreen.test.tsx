import { render, screen, fireEvent, within, act } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { OperatorScreen } from "./OperatorScreen";
import {
  makeTelemetry,
  makeSystem,
  makeMission,
  makeTarget,
  makeEvent,
} from "../test/factories";

const compact = vi.hoisted(() => ({ value: false }));
vi.mock("../hooks/useMediaQuery", async () => {
  const actual = await vi.importActual<typeof import("../hooks/useMediaQuery")>(
    "../hooks/useMediaQuery",
  );
  return { ...actual, useCompactLayout: () => compact.value };
});

/** The component's own props, so a fixture cannot drift from it. */
type Props = ComponentProps<typeof OperatorScreen>;

const base: Props = {
  telemetry: makeTelemetry(),
  events: [makeEvent()],
  connected: true,
  onAuthorize: vi.fn(),
  onReset: vi.fn(),
  onChangeSource: vi.fn(),
};

const screenOf = (props: Partial<Props> = {}) =>
  render(<OperatorScreen {...base} {...props} />).container;

beforeEach(() => {
  compact.value = false;
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe("header", () => {
  it("identifies the canister", () => {
    const container = screenOf();
    expect(screen.getByText("SkunkLabs")).toBeInTheDocument();
    // "Canister 01" also titles a status card, so scope to the header.
    const header = container.querySelector(".topbar") as HTMLElement;
    expect(within(header).getByText("Canister 01")).toBeInTheDocument();
  });

  it("summarises the active source and detector", () => {
    screenOf();
    expect(screen.getByTitle("Load different footage")).toHaveTextContent(
      "file:demo_drone.mp4 · motion",
    );
  });

  it("says 'source' before telemetry arrives", () => {
    screenOf({ telemetry: null });
    expect(screen.getByTitle("Load different footage")).toHaveTextContent("source");
  });

  it("reports the link state", () => {
    screenOf({ connected: true });
    expect(screen.getByText("System Online")).toBeInTheDocument();
  });

  it("reports reconnecting when the link drops", () => {
    screenOf({ connected: false });
    expect(screen.getByText("Reconnecting")).toBeInTheDocument();
  });

  it("shows the indicator bad unless both the link and the sensor are up", () => {
    const bothUp = screenOf({ connected: true });
    expect(bothUp.querySelector(".dot")).toHaveClass("is-ok");

    const sensorDown = screenOf({
      telemetry: makeTelemetry({ system: makeSystem({ sensor_online: false }) }),
    });
    expect(sensorDown.querySelector(".dot")).toHaveClass("is-bad");

    const linkDown = screenOf({ connected: false });
    expect(linkDown.querySelector(".dot")).toHaveClass("is-bad");
  });

  it("returns to source selection from the header", () => {
    const onChangeSource = vi.fn();
    screenOf({ onChangeSource });
    fireEvent.click(screen.getByTitle("Load different footage"));
    expect(onChangeSource).toHaveBeenCalled();
  });
});

describe("mission state", () => {
  it("renders the state the backend reports", () => {
    screenOf({
      telemetry: makeTelemetry({
        mission: makeMission({ state: "THREAT_CONFIRMED" }),
      }),
    });
    expect(screen.getByText("THREAT CONFIRMED")).toBeInTheDocument();
  });

  // Before the first frame the UI must not invent a state.
  it("falls back to SEARCHING with no telemetry", () => {
    screenOf({ telemetry: null });
    expect(screen.getByText("SEARCHING")).toBeInTheDocument();
  });

  it("picks the primary target for the readouts", () => {
    screenOf({
      telemetry: makeTelemetry({
        targets: [
          makeTarget({ target_id: "UAV-002", is_primary: false }),
          makeTarget({ target_id: "UAV-009", is_primary: true }),
        ],
      }),
    });
    expect(screen.getByText("UAV-009")).toBeInTheDocument();
  });

  it("shows NO TARGET when none is primary", () => {
    screenOf({
      telemetry: makeTelemetry({ targets: [makeTarget({ is_primary: false })] }),
    });
    expect(screen.getByText("NO TARGET")).toBeInTheDocument();
  });
});

describe("authorization", () => {
  it("arms the button only when the backend says so", () => {
    screenOf({
      telemetry: makeTelemetry({
        mission: makeMission({
          state: "AWAITING_AUTHORIZATION",
          can_authorize: true,
        }),
      }),
    });
    expect(screen.getByRole("button", { name: "Authorize" })).toBeEnabled();
  });

  it("authorizes via the space bar when armed", () => {
    const onAuthorize = vi.fn();
    screenOf({
      onAuthorize,
      telemetry: makeTelemetry({ mission: makeMission({ can_authorize: true }) }),
    });
    fireEvent.keyDown(window, { code: "Space" });
    expect(onAuthorize).toHaveBeenCalled();
  });

  // The hotkey is gated exactly like the button — it is not a way around the
  // interlock.
  it("ignores the space bar when not armed", () => {
    const onAuthorize = vi.fn();
    screenOf({
      onAuthorize,
      telemetry: makeTelemetry({ mission: makeMission({ can_authorize: false }) }),
    });
    fireEvent.keyDown(window, { code: "Space" });
    expect(onAuthorize).not.toHaveBeenCalled();
  });
});

describe("launch cue", () => {
  it("flashes on entering AUTHORIZED and clears itself", () => {
    const { rerender } = render(
      <OperatorScreen
        {...base}
        telemetry={makeTelemetry({ mission: makeMission({ state: "FOLLOWING" }) })}
      />,
    );
    expect(screen.queryByText("Launch Simulated")).not.toBeInTheDocument();

    rerender(
      <OperatorScreen
        {...base}
        telemetry={makeTelemetry({ mission: makeMission({ state: "AUTHORIZED" }) })}
      />,
    );
    expect(screen.getByText("Launch Simulated")).toBeInTheDocument();

    act(() => void vi.advanceTimersByTime(1600));
    expect(screen.queryByText("Launch Simulated")).not.toBeInTheDocument();
  });
});

describe("layout", () => {
  it("shows both side-panel sections on a wide screen", () => {
    compact.value = false;
    screenOf();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.getByText("Event Log")).toBeInTheDocument();
  });

  it("tabs the side panel on a narrow screen", () => {
    compact.value = true;
    screenOf();
    expect(screen.getByRole("tablist")).toBeInTheDocument();
  });
});

describe("controls", () => {
  it("resets the mission", () => {
    const onReset = vi.fn();
    screenOf({ onReset });
    fireEvent.click(screen.getByRole("button", { name: "Reset Mission" }));
    expect(onReset).toHaveBeenCalled();
  });
});
