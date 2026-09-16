import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useState, type ReactElement } from "react";
import { ErrorBoundary } from "./ErrorBoundary";
import { expectRenderErrors } from "../../test/helpers";

// These suites throw during render on purpose.
expectRenderErrors();

// React logs caught render errors itself; silence both that and the
// boundary's own componentDidCatch so a passing run stays readable.
let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => consoleError.mockRestore());

function Boom({ message = "telemetry shape changed" }): ReactElement {
  throw new Error(message);
}

describe("ErrorBoundary", () => {
  it("renders its children when nothing throws", () => {
    render(
      <ErrorBoundary label="Console">
        <p>video</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("video")).toBeInTheDocument();
  });

  it("shows the label and the error message instead of a white screen", () => {
    render(
      <ErrorBoundary label="Status panel">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Status panel unavailable")).toBeInTheDocument();
    expect(screen.getByText("telemetry shape changed")).toBeInTheDocument();
  });

  it("falls back to a generic label when none is given", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Panel unavailable")).toBeInTheDocument();
  });

  it("reports the failure to the console, named by label", () => {
    render(
      <ErrorBoundary label="Video">
        <Boom />
      </ErrorBoundary>,
    );
    expect(consoleError).toHaveBeenCalledWith(
      "[Video] render failed",
      expect.any(Error),
      expect.anything(),
    );
  });

  it("prefers a supplied fallback over the built-in one", () => {
    render(
      <ErrorBoundary label="Video" fallback={<p>no signal</p>}>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("no signal")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  // The retry button is the "way back" the docstring is about: without it a
  // transient bad frame strands the operator on the error card.
  it("Retry clears the error and re-renders the children", async () => {
    let shouldThrow = true;

    function Flaky() {
      const [, force] = useState(0);
      if (shouldThrow) {
        // Arm the recovery before throwing, so the retry finds a good child.
        setTimeout(() => {
          shouldThrow = false;
          force((n) => n + 1);
        }, 0);
        throw new Error("first render fails");
      }
      return <p>recovered</p>;
    }

    render(
      <ErrorBoundary label="Panel">
        <Flaky />
      </ErrorBoundary>,
    );
    expect(screen.getByText("first render fails")).toBeInTheDocument();

    await new Promise((r) => setTimeout(r, 10));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByText("recovered")).toBeInTheDocument();
  });
});
