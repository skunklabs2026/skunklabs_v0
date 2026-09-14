import { render, screen, fireEvent } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, it, expect, vi } from "vitest";
import { SidePanel } from "./SidePanel";
import { expectRenderErrors } from "../../test/helpers";
import {
  makeSystem,
  makeMission,
  makeTarget,
  makeEvent,
  makeIntercept,
} from "../../test/factories";

// This suite throws during render on purpose.
expectRenderErrors();

/** The component's own props, so a fixture cannot drift from it. */
type Props = ComponentProps<typeof SidePanel>;

const base: Props = {
  system: makeSystem(),
  mission: makeMission(),
  primary: makeTarget(),
  events: [makeEvent()],
  connected: true,
  intercept: makeIntercept(),
  interceptor: null,
  compact: false,
  onReset: vi.fn(),
  onChangeSource: vi.fn(),
};

const panel = (props: Partial<Props> = {}) =>
  render(<SidePanel {...base} {...props} />).container;

describe("wide layout", () => {
  it("shows status and the event log at once, with no tabs", () => {
    panel({ compact: false });
    expect(screen.getByText("Event Log")).toBeInTheDocument();
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });
});

describe("compact layout", () => {
  it("puts the two sections behind tabs so the video stays in view", () => {
    panel({ compact: true });
    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Status/ })).toBeInTheDocument();
  });

  it("opens on status, with the log hidden", () => {
    panel({ compact: true });
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.queryByText("Event Log")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Status/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("switches to the log and back", () => {
    panel({ compact: true });

    fireEvent.click(screen.getByRole("tab", { name: /Events/ }));
    expect(screen.getByText("Event Log")).toBeInTheDocument();
    expect(screen.queryByText("Target")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Events/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    fireEvent.click(screen.getByRole("tab", { name: /Status/ }));
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.queryByText("Event Log")).not.toBeInTheDocument();
  });

  // The count only means anything while the log is behind a tab.
  it("badges the Events tab with the entry count", () => {
    const container = panel({
      compact: true,
      events: [makeEvent(), makeEvent(), makeEvent()],
    });
    expect(container.querySelector(".tab-count")).toHaveTextContent("3");
  });

  it("omits the badge when there is nothing to read", () => {
    const container = panel({ compact: true, events: [] });
    expect(container.querySelector(".tab-count")).toBeNull();
  });

  it("marks the active tab", () => {
    const container = panel({ compact: true });
    expect(container.querySelectorAll(".panel-tab.is-active")).toHaveLength(1);
  });
});

describe("controls", () => {
  it("resets the mission", () => {
    const onReset = vi.fn();
    panel({ onReset });
    fireEvent.click(screen.getByRole("button", { name: "Reset Mission" }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("returns to source selection", () => {
    const onChangeSource = vi.fn();
    panel({ onChangeSource });
    fireEvent.click(screen.getByRole("button", { name: "Change Source" }));
    expect(onChangeSource).toHaveBeenCalledTimes(1);
  });

  it("stays available in compact mode, under either tab", () => {
    panel({ compact: true });
    expect(
      screen.getByRole("button", { name: "Reset Mission" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Events/ }));
    expect(
      screen.getByRole("button", { name: "Reset Mission" }),
    ).toBeInTheDocument();
  });
});

// Each section is wrapped separately so one bad readout cannot blank the
// whole console.
describe("fault isolation", () => {
  it("keeps the event log and controls when the status panel throws", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    // A platform the label map does not know makes StatusPanel's lookup throw.
    panel({
      primary: makeTarget({ platform: "NONSENSE" as never, platform_label: "?" }),
      system: null,
      mission: null,
    });

    // Whatever happened to Status, the rest of the column survived.
    expect(screen.getByText("Event Log")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reset Mission" }),
    ).toBeInTheDocument();
    consoleError.mockRestore();
  });
});
