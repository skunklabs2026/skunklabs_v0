import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { EventLog } from "./EventLog";
import { makeEvent, ALL_EVENT_KINDS } from "../../test/factories";

/** jsdom has no layout, so scroll geometry has to be supplied by hand. */
function setGeometry(
  node: HTMLElement,
  { scrollHeight = 1000, clientHeight = 200, scrollTop = 0 } = {},
) {
  Object.defineProperty(node, "scrollHeight", {
    value: scrollHeight,
    configurable: true,
  });
  Object.defineProperty(node, "clientHeight", {
    value: clientHeight,
    configurable: true,
  });
  node.scrollTop = scrollTop;
}

describe("EventLog", () => {
  it("shows a placeholder before any telemetry arrives", () => {
    render(<EventLog events={[]} />);
    expect(screen.getByText("Awaiting telemetry…")).toBeInTheDocument();
    expect(screen.getByText("--:--:--")).toBeInTheDocument();
  });

  it("renders each event's message with a timestamp", () => {
    render(
      <EventLog
        events={[
          makeEvent({ message: "UAV-001 detected at 85% confidence." }),
          makeEvent({ message: "Track acquired." }),
        ]}
      />,
    );
    expect(
      screen.getByText("UAV-001 detected at 85% confidence."),
    ).toBeInTheDocument();
    expect(screen.getByText("Track acquired.")).toBeInTheDocument();
    expect(screen.getAllByText(/^\d{2}:\d{2}:\d{2}$/)).toHaveLength(2);
  });

  it("drops the placeholder once events exist", () => {
    render(<EventLog events={[makeEvent()]} />);
    expect(screen.queryByText("Awaiting telemetry…")).not.toBeInTheDocument();
  });

  // The reference document requires each event kind to be distinguishable.
  it.each(ALL_EVENT_KINDS)("tags a %s event with its kind class", (kind) => {
    const { container } = render(
      <EventLog events={[makeEvent({ kind, message: `a ${kind} event` })]} />,
    );
    expect(container.querySelector(`.log-entry.kind-${kind}`)).toBeInTheDocument();
  });

  it("keeps entries with identical timestamps distinct", () => {
    const { container } = render(
      <EventLog
        events={[
          makeEvent({ timestamp: 5, message: "first" }),
          makeEvent({ timestamp: 5, message: "second" }),
        ]}
      />,
    );
    expect(container.querySelectorAll(".log-entry")).toHaveLength(2);
  });

  describe("auto-scroll", () => {
    it("follows the tail as events arrive", () => {
      const { container, rerender } = render(<EventLog events={[makeEvent()]} />);
      const scroller = container.querySelector(".log-scroll") as HTMLElement;
      setGeometry(scroller);

      rerender(<EventLog events={[makeEvent(), makeEvent({ message: "next" })]} />);
      expect(scroller.scrollTop).toBe(1000);
    });

    // Yanking the view away while the operator is reading is hostile.
    it("stops following once the operator scrolls up to read", () => {
      const { container, rerender } = render(<EventLog events={[makeEvent()]} />);
      const scroller = container.querySelector(".log-scroll") as HTMLElement;

      // Scrolled well away from the bottom.
      setGeometry(scroller, {
        scrollHeight: 1000,
        clientHeight: 200,
        scrollTop: 100,
      });
      fireEvent.scroll(scroller);

      rerender(<EventLog events={[makeEvent(), makeEvent({ message: "next" })]} />);
      expect(scroller.scrollTop).toBe(100);
    });

    it("resumes following when scrolled back near the bottom", () => {
      const { container, rerender } = render(<EventLog events={[makeEvent()]} />);
      const scroller = container.querySelector(".log-scroll") as HTMLElement;

      setGeometry(scroller, {
        scrollHeight: 1000,
        clientHeight: 200,
        scrollTop: 100,
      });
      fireEvent.scroll(scroller);

      // Within 24px of the bottom counts as pinned.
      setGeometry(scroller, {
        scrollHeight: 1000,
        clientHeight: 200,
        scrollTop: 790,
      });
      fireEvent.scroll(scroller);

      rerender(<EventLog events={[makeEvent(), makeEvent({ message: "next" })]} />);
      expect(scroller.scrollTop).toBe(1000);
    });
  });
});
