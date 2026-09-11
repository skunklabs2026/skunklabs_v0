import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Row, Dot, Meter, StatusDot } from "./Readout";

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

describe("StatusDot", () => {
  it.each([
    ["ok", "is-ok"],
    ["bad", "is-bad"],
    ["unknown", "is-unknown"],
  ] as const)("renders the %s tone", (tone, className) => {
    render(<StatusDot tone={tone} />);
    expect(document.querySelector(".dot")).toHaveClass(className);
  });

  it("gives 'unknown' its own tone rather than reusing 'bad'", () => {
    // A canister subsystem with no sensor attached has nothing to report; it
    // is not unhealthy. Colouring that as a fault trains an operator to
    // ignore faults.
    render(<StatusDot tone="unknown" />);
    const dot = document.querySelector(".dot");
    expect(dot).not.toHaveClass("is-bad");
    expect(dot).not.toHaveClass("is-ok");
  });

  it("is hidden from assistive tech, since the label carries the meaning", () => {
    render(<StatusDot tone="ok" />);
    expect(document.querySelector(".dot")).toHaveAttribute("aria-hidden", "true");
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
