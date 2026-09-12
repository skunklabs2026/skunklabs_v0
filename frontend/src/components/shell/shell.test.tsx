import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  fakeStore,
  makeDecisionSnapshot,
  makeInterceptor,
  makeSnapshot,
  makeTrack,
} from "../../test/fixtures";
import { renderWithStore } from "../../test/render";
import { ConnectionOverlay } from "./ConnectionOverlay";
import { DemoControls } from "./DemoControls";
import { MissionBar } from "./MissionBar";
import { TopBar } from "./TopBar";

const button = (name: RegExp) => screen.getByRole("button", { name });

describe("MissionBar", () => {
  const counters = () =>
    Object.fromEntries(
      screen
        .getAllByRole("listitem")
        .map((item) => [
          item.textContent?.replace(/^\d+/, "") ?? "",
          item.textContent,
        ]),
    );

  it("waits for a connection", () => {
    renderWithStore(<MissionBar />, fakeStore().store);
    expect(
      screen.getByText(/connecting to the defense system/i),
    ).toBeInTheDocument();
    expect(screen.getByText("T+00:00")).toBeInTheDocument();
  });

  it("counts the whole mission and says what is happening", () => {
    const { store } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<MissionBar />, store);

    expect(counters()).toMatchObject({
      Threats: "3Threats",
      "Inside area": "2Inside area",
      "Awaiting decision": "2Awaiting decision",
      "In flight": "0In flight",
    });
    expect(screen.getByText("T+00:09")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      /Running.*2 responses awaiting operator decision/,
    );
  });

  it("lights only the counters that matter", () => {
    const { store } = fakeStore({
      snapshot: makeDecisionSnapshot({
        decision_queue: [],
        interceptors: [makeInterceptor()],
        tracks: [makeTrack({ status: "INTERCEPTED" })],
      }),
    });
    renderWithStore(<MissionBar />, store);
    const lit = screen
      .getAllByRole("listitem")
      .filter((item) => item.className.includes("is-lit"))
      .map((item) => item.textContent);
    expect(lit).toEqual(["1In flight", "1Intercepted"]);
  });
});

describe("DemoControls", () => {
  it("chooses a scenario and starts the demo", () => {
    const { store, command } = fakeStore({ snapshot: makeSnapshot() });
    renderWithStore(<DemoControls />, store);

    const select = screen.getByRole("combobox", { name: /threat scenario/i });
    expect(select).toHaveValue("S1");
    fireEvent.change(select, { target: { value: "S3" } });
    expect(command).toHaveBeenCalledWith("configure", {
      body: { scenario_id: "S3" },
    });

    fireEvent.click(button(/start demo/i));
    expect(command).toHaveBeenCalledWith("start");
  });

  it("offers reset once running, as the primary action when finished", () => {
    const running = fakeStore({ snapshot: makeDecisionSnapshot() });
    const { unmount } = renderWithStore(<DemoControls />, running.store);
    expect(
      screen.getByRole("combobox", { name: /threat scenario/i }),
    ).toBeDisabled();
    expect(button(/reset demo/i)).not.toHaveClass("c-btn-primary");
    fireEvent.click(button(/reset demo/i));
    expect(running.command).toHaveBeenCalledWith("reset");
    unmount();

    const done = fakeStore({
      snapshot: makeDecisionSnapshot({ state: "COMPLETE", running: false }),
    });
    renderWithStore(<DemoControls />, done.store);
    expect(button(/reset demo/i)).toHaveClass("c-btn-primary");
  });

  it("is disabled without a live backend", () => {
    renderWithStore(<DemoControls />, fakeStore({ connection: "offline" }).store);
    expect(button(/start demo/i)).toBeDisabled();
  });

  it("labels pending commands", () => {
    renderWithStore(
      <DemoControls />,
      fakeStore({ snapshot: makeSnapshot(), pending: "start" }).store,
    );
    expect(button(/starting/i)).toBeDisabled();
  });
});

describe("TopBar", () => {
  it("links the two views and reports site, mission and link", () => {
    const { store } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<TopBar route="launcher" />, store);

    const launcher = screen.getByRole("link", { name: "Launcher" });
    expect(launcher).toHaveAttribute("href", "/launcher");
    expect(launcher).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Map" })).not.toHaveAttribute(
      "aria-current",
    );

    expect(screen.getByText("SITE-A")).toBeInTheDocument();
    expect(screen.getByText("Your location")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Online")).toBeInTheDocument();
    expect(screen.getByText(/simulation · ×20/i)).toBeInTheDocument();
  });

  it("says when the location is the default and the backend is offline", () => {
    const snapshot = makeSnapshot();
    const { store } = fakeStore({
      snapshot: {
        ...snapshot,
        site: { ...snapshot.site, location_source: "DEFAULT" },
      },
      connection: "offline",
    });
    renderWithStore(<TopBar route="map" />, store);
    expect(screen.getByText("Default location")).toBeInTheDocument();
    expect(screen.getByText("Backend offline")).toBeInTheDocument();
  });
});

describe("ConnectionOverlay", () => {
  it("distinguishes connecting from offline", () => {
    const { rerender } = render(<ConnectionOverlay connection="connecting" />);
    expect(screen.getByRole("status")).toHaveTextContent(/connecting/i);
    rerender(<ConnectionOverlay connection="offline" />);
    expect(
      within(screen.getByRole("status")).getByText(/backend offline/i),
    ).toBeInTheDocument();
  });
});
