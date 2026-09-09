import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Row, Dot, Meter } from "./Readout";

describe("Row", () => {
  it("renders label and value", () => {
    render(<Row label="Status" value="Active" />);
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("applies muted class when muted prop is true", () => {
    render(<Row label="Status" value="Inactive" muted />);
    const valueEl = screen.getByText("Inactive");
    expect(valueEl).toHaveClass("is-muted");
  });

  it("does not apply muted class by default", () => {
    render(<Row label="Status" value="Active" />);
    const valueEl = screen.getByText("Active");
    expect(valueEl).not.toHaveClass("is-muted");
  });
});

describe("Dot", () => {
  it("renders with ok state", () => {
    render(<Dot ok={true} label="Connected" />);
    expect(screen.getByText("Connected")).toBeInTheDocument();
    const dot = document.querySelector(".dot");
    expect(dot).toHaveClass("is-ok");
  });

  it("renders with bad state", () => {
    render(<Dot ok={false} label="Disconnected" />);
    expect(screen.getByText("Disconnected")).toBeInTheDocument();
    const dot = document.querySelector(".dot");
    expect(dot).toHaveClass("is-bad");
  });
});

describe("Meter", () => {
  it("renders with correct fill width", () => {
    render(<Meter value={0.5} />);
    const fill = document.querySelector(".meter-fill") as HTMLElement;
    expect(fill.style.width).toBe("50%");
  });

  it("clamps value to 0-100%", () => {
    const { rerender } = render(<Meter value={1.5} />);
    let fill = document.querySelector(".meter-fill") as HTMLElement;
    expect(fill.style.width).toBe("100%");

    rerender(<Meter value={-0.5} />);
    fill = document.querySelector(".meter-fill") as HTMLElement;
    expect(fill.style.width).toBe("0%");
  });
});
