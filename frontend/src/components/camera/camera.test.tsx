import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ScenarioSnapshot } from "../../scenario/contract";
import {
  fakeStore,
  makeDecisionSnapshot,
  makeEngagement,
  makeSnapshot,
  makeTrack,
  withNode,
} from "../../test/fixtures";
import { renderWithStore } from "../../test/render";
import { SimulatedCameraView } from "./SimulatedCameraView";

/** NODE-02 answering T-001, pointing wherever `yaw` says. */
function watching(yaw: number, overrides: Partial<ScenarioSnapshot> = {}) {
  const snapshot = makeDecisionSnapshot(overrides);
  return fakeStore({
    snapshot: {
      ...snapshot,
      nodes: withNode(snapshot.nodes, "NODE-02", {
        current_yaw_deg: yaw,
        current_pitch_deg: 12,
      }),
    },
  }).store;
}

describe("SimulatedCameraView", () => {
  it("renders nothing without data, or for an unknown node", () => {
    const empty = renderWithStore(
      <SimulatedCameraView nodeId="NODE-02" />,
      fakeStore().store,
    );
    expect(empty.container).toBeEmptyDOMElement();
    empty.unmount();

    const unknown = renderWithStore(
      <SimulatedCameraView nodeId="NODE-99" />,
      watching(81.3),
    );
    expect(unknown.container).toBeEmptyDOMElement();
  });

  it("turns with the node and shows its elevation", () => {
    renderWithStore(<SimulatedCameraView nodeId="NODE-02" />, watching(81.3));
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "Simulated camera at NODE-02, heading 081.3°",
    );
    expect(screen.getByText("EL 12.0°")).toBeInTheDocument();
  });

  it("boxes the threat it is slaved to", () => {
    renderWithStore(<SimulatedCameraView nodeId="NODE-02" />, watching(81.3));
    expect(screen.getByTestId("camera-track")).toHaveTextContent("T-001 · 21.9 km");
    expect(screen.getByText(/TRACKING T-001/)).toBeInTheDocument();
    expect(screen.getByText(/RNG 21\.9 KM/)).toBeInTheDocument();
  });

  it("points to the threat when it is outside the field of view", () => {
    renderWithStore(<SimulatedCameraView nodeId="NODE-02" />, watching(0));
    expect(screen.queryByTestId("camera-track")).toBeNull();
    expect(screen.getByTestId("camera-track-offscreen")).toHaveTextContent("T-001");
  });

  it("marks a simulated intercept and drops a threat that reached the site", () => {
    const intercepted = renderWithStore(
      <SimulatedCameraView nodeId="NODE-02" />,
      watching(81.3, {
        tracks: [makeTrack({ status: "INTERCEPTED", engagement_id: "R-01" })],
        engagements: [makeEngagement({ status: "INTERCEPTED" })],
      }),
    );
    expect(screen.getByTestId("camera-track")).toHaveTextContent(
      "SIMULATED INTERCEPT",
    );
    intercepted.unmount();

    renderWithStore(
      <SimulatedCameraView nodeId="NODE-02" />,
      watching(81.3, {
        tracks: [makeTrack({ status: "REACHED_SITE", engagement_id: "R-01" })],
        engagements: [makeEngagement({ status: "ABORTED" })],
      }),
    );
    expect(screen.queryByTestId("camera-track")).toBeNull();
  });

  it("watches its sector when the node has no response", () => {
    const snapshot = makeSnapshot();
    const store = fakeStore({
      snapshot: {
        ...snapshot,
        nodes: withNode(snapshot.nodes, "NODE-02", { current_yaw_deg: 60 }),
      },
    }).store;
    renderWithStore(<SimulatedCameraView nodeId="NODE-02" />, store);
    expect(screen.queryByTestId("camera-track")).toBeNull();
    expect(screen.getByText(/SECTOR SCAN/)).toBeInTheDocument();
    expect(screen.getByText("NODE-02 EO")).toBeInTheDocument();
  });
});
