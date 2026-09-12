import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  fakeStore,
  makeDecisionSnapshot,
  makeEngagement,
  makeInterceptor,
  makeSnapshot,
  makeTrack,
  withNode,
} from "../../test/fixtures";
import { renderWithStore } from "../../test/render";
import { AxisReadout } from "./AxisReadout";
import { DecisionPanel } from "./DecisionPanel";
import { EventLog } from "./EventLog";
import { InterceptorList } from "./InterceptorList";
import { NodeList } from "./NodeList";
import { NodeTabs } from "./NodeTabs";
import { ScenarioPicker } from "./ScenarioPicker";
import { SitePanel } from "./SitePanel";
import { ThreatList } from "./ThreatList";

const button = (name: RegExp) => screen.getByRole("button", { name });

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("EventLog", () => {
  it("says so when empty", () => {
    renderWithStore(<EventLog />, fakeStore().store);
    expect(screen.getByText(/no events yet/i)).toBeInTheDocument();
  });

  it("lists events in order with their time", () => {
    const at = (s: number) => new Date(2024, 9, 26, 14, 32, s).getTime() / 1000;
    const { store } = fakeStore({
      snapshot: makeSnapshot({
        events: [
          { timestamp: at(11), message: "4 nodes activated - NODE-01, NODE-02" },
          { timestamp: at(12), message: "R-01 proposed - NODE-02 → T-001" },
        ],
      }),
    });
    renderWithStore(<EventLog />, store);
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(
      "14:32:114 nodes activated - NODE-01, NODE-02",
    );
    expect(items[1]).toHaveTextContent("14:32:12R-01 proposed - NODE-02 → T-001");
  });
});

describe("ScenarioPicker", () => {
  it("offers the three threat scenarios and selects one", () => {
    const { store, command } = fakeStore({ snapshot: makeSnapshot() });
    renderWithStore(<ScenarioPicker />, store);

    const options = screen.getAllByRole("radio");
    expect(options.map((o) => o.textContent)).toEqual([
      "Scenario 14 drones approaching from the east4 threats",
      "Scenario 23 drones from the east, 3 from the west6 threats",
      "Scenario 34 drones from the north, 2 from the southeast6 threats",
    ]);
    expect(options[0]).toHaveAttribute("aria-checked", "true");

    fireEvent.click(options[1]);
    expect(command).toHaveBeenCalledWith("configure", {
      body: { scenario_id: "S2" },
    });
  });

  it("locks once the mission is running", () => {
    const { store } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<ScenarioPicker />, store);
    expect(screen.getAllByRole("radio")[1]).toBeDisabled();
    expect(
      screen.getByText(/reset the demo to choose another scenario/i),
    ).toBeInTheDocument();
  });
});

describe("DecisionPanel", () => {
  const selected = () => screen.getByLabelText("Interceptors selected");

  it("waits for threats before proposing anything", () => {
    renderWithStore(
      <DecisionPanel />,
      fakeStore({ snapshot: makeSnapshot() }).store,
    );
    expect(
      screen.getByText(
        /responses are proposed when threats enter the protected area/i,
      ),
    ).toBeInTheDocument();
  });

  it("presents one response at a time, with what comes next", () => {
    const { store } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<DecisionPanel />, store);

    expect(screen.getByText("2 pending")).toBeInTheDocument();
    expect(screen.getByText("Response 1 of 2")).toBeInTheDocument();
    expect(screen.getByText("R-01")).toBeInTheDocument();
    expect(screen.getByText("NODE-02")).toBeInTheDocument();
    expect(screen.getByText("T-001")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("37.6 km")).toBeInTheDocument();

    const next = within(screen.getByRole("list"));
    expect(next.getByText("R-02")).toBeInTheDocument();
    expect(next.getByText("NODE-03 → T-002")).toBeInTheDocument();
    expect(next.getByText("Node orienting")).toBeInTheDocument();
  });

  it("authorizes the proposed count, or one the operator chooses", () => {
    const { store, command, setInterceptorRequest } = fakeStore({
      snapshot: makeDecisionSnapshot(),
    });
    renderWithStore(<DecisionPanel />, store);

    expect(selected()).toHaveTextContent("2");
    expect(screen.getByText("Proposed 2 · 6 at NODE-02")).toBeInTheDocument();

    fireEvent.click(button(/more interceptors/i));
    expect(setInterceptorRequest).toHaveBeenCalledWith("R-01", 3);
    expect(selected()).toHaveTextContent("3");

    fireEvent.click(button(/authorize simulation/i));
    expect(command).toHaveBeenCalledWith("authorize", {
      engagementId: "R-01",
      body: { interceptors: 3 },
    });
  });

  it("declines the presented response", () => {
    const { store, command } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<DecisionPanel />, store);
    fireEvent.click(button(/decline/i));
    expect(command).toHaveBeenCalledWith("decline", { engagementId: "R-01" });
  });

  it("cannot authorize until the node has finished orienting", () => {
    const { store } = fakeStore({
      snapshot: makeDecisionSnapshot({ decision_queue: ["R-02"] }),
    });
    renderWithStore(<DecisionPanel />, store);
    expect(button(/authorize simulation/i)).toBeDisabled();
    expect(screen.getByText(/NODE-03 orienting, 11\.5° to go/)).toBeInTheDocument();
    expect(button(/decline/i)).toBeEnabled();
  });

  it("never offers more interceptors than the node holds", () => {
    const snapshot = makeDecisionSnapshot();
    const { store } = fakeStore({
      snapshot: {
        ...snapshot,
        nodes: withNode(snapshot.nodes, "NODE-02", { inventory: 3 }),
      },
      interceptorRequests: { "R-01": 9 },
    });
    renderWithStore(<DecisionPanel />, store);
    expect(selected()).toHaveTextContent("3");
    expect(button(/more interceptors/i)).toBeDisabled();
  });

  it("reports a rejection and disables while offline", () => {
    const { store } = fakeStore({
      snapshot: makeDecisionSnapshot(),
      connection: "offline",
      error: "Authorization rejected - R-01 is PROPOSED.",
    });
    renderWithStore(<DecisionPanel />, store);
    expect(screen.getByRole("alert")).toHaveTextContent("R-01 is PROPOSED.");
    expect(button(/authorize simulation/i)).toBeDisabled();
    expect(button(/decline/i)).toBeDisabled();
  });

  it("offers every free node, nearest first, and hands the response over", () => {
    const { store, command } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<DecisionPanel />, store);

    const select = screen.getByLabelText(/launching node/i);
    const options = within(select).getAllByRole("option");
    // NODE-02 is assigned and nearest; NODE-03 is busy with R-02, so it is out.
    expect(options).toHaveLength(5);
    expect(options[0]).toHaveValue("NODE-02");
    expect(options.map((o) => o.getAttribute("value"))).not.toContain("NODE-03");
    expect(options[0]).toHaveTextContent(/NODE-02 · [\d.]+ km · 6 ready/);

    const distances = options.map((option) =>
      Number(/· ([\d.]+) km/.exec(option.textContent ?? "")?.[1]),
    );
    expect(distances).toEqual([...distances].sort((a, b) => a - b));

    fireEvent.change(select, {
      target: { value: options[2].getAttribute("value") },
    });
    expect(command).toHaveBeenCalledWith("reassign", {
      engagementId: "R-01",
      body: { node_id: options[2].getAttribute("value") },
    });
  });

  it("says when nothing is pending", () => {
    const { store } = fakeStore({
      snapshot: makeDecisionSnapshot({ decision_queue: [] }),
    });
    renderWithStore(<DecisionPanel />, store);
    expect(screen.getByText(/no decisions pending/i)).toBeInTheDocument();
  });
});

describe("SitePanel", () => {
  const stubGeolocation = (value: unknown) =>
    Object.defineProperty(navigator, "geolocation", { value, configurable: true });

  afterEach(() => stubGeolocation(undefined));

  it("shows where the site is and where that came from", () => {
    const { store } = fakeStore({ snapshot: makeSnapshot() });
    renderWithStore(<SitePanel />, store);
    expect(screen.getByText("This device")).toBeInTheDocument();
    expect(screen.getByText("49.99300")).toBeInTheDocument();
    expect(screen.getByText("36.23000")).toBeInTheDocument();
  });

  it("explains a refused browser position and still offers a way to set one", () => {
    const snapshot = makeSnapshot();
    const { store } = fakeStore({
      snapshot: {
        ...snapshot,
        site: { ...snapshot.site, location_source: "DEFAULT" },
      },
      location: "unavailable",
    });
    renderWithStore(<SitePanel />, store);
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.getByText(/this browser gave no position/i)).toBeInTheDocument();
  });

  it("does not call a hand-entered position a device position", () => {
    // The backend marks any operator-supplied position DEVICE; only this
    // client knows the browser never reported one.
    const { store } = fakeStore({
      snapshot: makeSnapshot(),
      location: "unavailable",
    });
    renderWithStore(<SitePanel />, store);
    expect(screen.getByText("Operator set")).toBeInTheDocument();
    expect(
      screen.getByText(/centred on the coordinates you set/i),
    ).toBeInTheDocument();
  });

  it("re-asks the browser on request", async () => {
    stubGeolocation({
      getCurrentPosition: (success: PositionCallback) =>
        success({
          coords: { latitude: 45.4642, longitude: 9.19 },
        } as GeolocationPosition),
    });
    const { store, command, setLocation } = fakeStore({ snapshot: makeSnapshot() });
    renderWithStore(<SitePanel />, store);

    fireEvent.click(button(/use my location/i));
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("configure", {
        body: { latitude: 45.4642, longitude: 9.19 },
        quiet: true,
      }),
    );
    expect(setLocation).toHaveBeenLastCalledWith("device");
  });

  it("accepts coordinates typed in by the operator", () => {
    const { store, command } = fakeStore({ snapshot: makeSnapshot() });
    renderWithStore(<SitePanel />, store);

    const set = button(/^set$/i);
    expect(set).toBeDisabled(); // nothing typed yet
    fireEvent.change(screen.getByLabelText(/^latitude$/i), {
      target: { value: "45.4642" },
    });
    fireEvent.change(screen.getByLabelText(/^longitude$/i), {
      target: { value: "9.19" },
    });
    fireEvent.click(set);

    expect(command).toHaveBeenCalledWith("configure", {
      body: { latitude: 45.4642, longitude: 9.19 },
    });
  });

  it("locks once the mission is running", () => {
    const { store } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<SitePanel />, store);
    expect(button(/use my location/i)).toBeDisabled();
    expect(
      screen.getByText(/reset the demo to move the site/i),
    ).toBeInTheDocument();
  });
});

describe("ThreatList", () => {
  it("shows each threat's distance to the site and who is answering it", () => {
    const { store } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<ThreatList />, store);

    expect(screen.getByText("2 inside area")).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("T-00137.6 kmNODE-02 · Awaiting decision");
    expect(rows[1]).toHaveTextContent("T-00237.8 kmNODE-03 · Node orienting");
    expect(rows[2]).toHaveTextContent("T-00341.2 kmOutside area");
  });

  it("shows outcomes once a threat is resolved", () => {
    const { store } = fakeStore({
      snapshot: makeDecisionSnapshot({
        tracks: [makeTrack({ status: "INTERCEPTED" })],
        decision_queue: [],
      }),
    });
    renderWithStore(<ThreatList />, store);
    expect(screen.getByRole("listitem")).toHaveTextContent(
      "T-001-Intercepted · sim",
    );
  });

  it("says when nothing has been detected", () => {
    renderWithStore(<ThreatList />, fakeStore({ snapshot: makeSnapshot() }).store);
    expect(screen.getByText(/no threats detected/i)).toBeInTheDocument();
  });
});

describe("NodeList", () => {
  it("lists all six nodes with state and inventory", () => {
    const { store } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<NodeList />, store);

    expect(screen.getByText("2 active")).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(6);
    expect(rows[1]).toHaveTextContent("NODE-02Ready · T-001");
    expect(
      within(rows[1]).getByLabelText("6 of 6 interceptors"),
    ).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent("NODE-01Standby");
  });

  it("opens a node in the launcher view", () => {
    const { store, selectNode } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<NodeList />, store);
    fireEvent.click(button(/open NODE-03 in the launcher view/i));
    expect(selectNode).toHaveBeenCalledWith("NODE-03");
    expect(window.location.pathname).toBe("/launcher");
  });
});

describe("NodeTabs", () => {
  it("follows the current decision until the operator picks a node", () => {
    const { store, selectNode } = fakeStore({ snapshot: makeDecisionSnapshot() });
    renderWithStore(<NodeTabs />, store);

    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(6);
    expect(tabs[1]).toHaveAttribute("aria-selected", "true"); // NODE-02, being decided
    expect(
      screen.getByRole("checkbox", { name: /follow current decision/i }),
    ).toBeChecked();

    fireEvent.click(tabs[4]);
    expect(selectNode).toHaveBeenCalledWith("NODE-05");
    expect(screen.getAllByRole("tab")[4]).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("checkbox", { name: /follow current decision/i }),
    ).not.toBeChecked();
  });

  it("goes back to following", () => {
    const { store, selectNode } = fakeStore({
      snapshot: makeDecisionSnapshot(),
      selectedNodeId: "NODE-05",
    });
    renderWithStore(<NodeTabs />, store);
    fireEvent.click(
      screen.getByRole("checkbox", { name: /follow current decision/i }),
    );
    expect(selectNode).toHaveBeenCalledWith(null);
  });
});

describe("InterceptorList", () => {
  it("shows each interceptor, its threat and its status", () => {
    renderWithStore(
      <InterceptorList
        interceptors={[
          makeInterceptor({ state: "INTERCEPT" }),
          makeInterceptor({ id: "INT-002", state: "STOOD_DOWN" }),
          makeInterceptor({ id: "INT-003", state: "PENDING" }),
          makeInterceptor({ id: "INT-004" }),
        ]}
      />,
      fakeStore().store,
    );
    expect(screen.getAllByRole("listitem").map((row) => row.textContent)).toEqual([
      "INT-001→ T-001Intercept · sim",
      "INT-002→ T-001Stood down",
      "INT-003→ T-001Queued",
      "INT-004→ T-001In flight",
    ]);
  });

  it("says when nothing is assigned", () => {
    renderWithStore(<InterceptorList interceptors={[]} />, fakeStore().store);
    expect(screen.getByText(/no interceptors assigned/i)).toBeInTheDocument();
  });
});

describe("AxisReadout", () => {
  it("shows yaw with the shortest-way error", () => {
    renderWithStore(
      <AxisReadout kind="yaw" current={350} requested={10} />,
      fakeStore().store,
    );
    const yaw = screen.getByRole("region", { name: "Yaw" });
    expect(within(yaw).getByTestId("yaw-current")).toHaveTextContent("350.0°");
    expect(within(yaw).getByTestId("yaw-requested")).toHaveTextContent("010.0°");
    expect(within(yaw).getByText("20.0°")).toBeInTheDocument();
  });

  it("shows pitch as an elevation", () => {
    renderWithStore(
      <AxisReadout kind="pitch" current={3.5} requested={12} />,
      fakeStore().store,
    );
    expect(screen.getByTestId("pitch-current")).toHaveTextContent("3.5°");
    expect(screen.getByText("8.5°")).toBeInTheDocument();
  });
});

describe("engagement fixtures", () => {
  it("keep the decision snapshot honest", () => {
    // Guards the fixture the panel tests lean on: R-01 is the head of the queue.
    expect(makeEngagement().status).toBe("AWAITING_AUTHORIZATION");
    expect(makeDecisionSnapshot().decision_queue[0]).toBe("R-01");
  });
});
