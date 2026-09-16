import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { DetectorChoice } from "./DetectorChoice";

const base = {
  available: ["motion", "yolo"],
  active: "motion",
  threshold: 0.55,
  busy: false,
  onSelect: vi.fn(),
  onThreshold: vi.fn(),
};

const choice = (props: Partial<typeof base> = {}) =>
  render(<DetectorChoice {...base} {...props} />).container;

describe("DetectorChoice", () => {
  it("offers every detector the backend reports", () => {
    choice();
    expect(screen.getByText("motion")).toBeInTheDocument();
    expect(screen.getByText("yolo")).toBeInTheDocument();
  });

  it("describes what each detector is for", () => {
    choice();
    expect(screen.getByText(/Background subtraction/)).toBeInTheDocument();
    expect(screen.getByText(/YOLO26n neural detector/)).toBeInTheDocument();
  });

  it("renders an unknown detector without a blurb rather than crashing", () => {
    choice({ available: ["experimental"] });
    expect(screen.getByText("experimental")).toBeInTheDocument();
  });

  it("marks only the active detector", () => {
    const container = choice({ active: "yolo" });
    const on = container.querySelectorAll(".detector-card.is-on");
    expect(on).toHaveLength(1);
    expect(on[0]).toHaveTextContent("yolo");
  });

  it("selects a detector on click", () => {
    const onSelect = vi.fn();
    choice({ onSelect });
    fireEvent.click(screen.getByText("yolo"));
    expect(onSelect).toHaveBeenCalledWith("yolo");
  });

  it("disables the cards and the slider while a change is in flight", () => {
    const container = choice({ busy: true });
    container.querySelectorAll(".detector-card").forEach((card) => {
      expect(card).toBeDisabled();
    });
    expect(screen.getByLabelText("Detection confidence threshold")).toBeDisabled();
  });

  it("shows the threshold to two decimals", () => {
    choice({ threshold: 0.5 });
    expect(screen.getByText("0.50")).toBeInTheDocument();
  });

  it("reports a new threshold as a number, not a string", () => {
    const onThreshold = vi.fn();
    choice({ onThreshold });
    fireEvent.change(screen.getByLabelText("Detection confidence threshold"), {
      target: { value: "0.75" },
    });
    expect(onThreshold).toHaveBeenCalledWith(0.75);
  });

  it("constrains the slider to the backend's usable range", () => {
    choice();
    const slider = screen.getByLabelText("Detection confidence threshold");
    expect(slider).toHaveAttribute("min", "0.05");
    expect(slider).toHaveAttribute("max", "0.9");
    expect(slider).toHaveAttribute("step", "0.05");
  });

  it("explains which way to move the threshold", () => {
    choice();
    expect(
      screen.getByText(/Lower it if a small or distant target is missed/),
    ).toBeInTheDocument();
  });
});
