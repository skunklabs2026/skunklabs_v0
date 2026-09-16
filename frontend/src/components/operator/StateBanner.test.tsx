import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StateBanner } from "./StateBanner";
import { makeMission, ALL_STATES } from "../../test/factories";
import { STATE_LABEL } from "../../format";

describe("StateBanner", () => {
  it.each(ALL_STATES)("renders the operator label for %s", (state) => {
    render(
      <StateBanner
        state={state}
        mission={makeMission({ state })}
        onAuthorize={vi.fn()}
      />,
    );
    expect(screen.getByText(STATE_LABEL[state])).toBeInTheDocument();
  });

  it("shows the backend's detail line", () => {
    render(
      <StateBanner
        state="TRACKING"
        mission={makeMission({ detail: "Evaluating demo criteria." })}
        onAuthorize={vi.fn()}
      />,
    );
    expect(screen.getByText("Evaluating demo criteria.")).toBeInTheDocument();
  });

  it("says it is connecting before the first frame arrives", () => {
    render(<StateBanner state="SEARCHING" mission={null} onAuthorize={vi.fn()} />);
    expect(screen.getByText("Connecting to canister…")).toBeInTheDocument();
  });

  // The interlock: the button's enabled state is the backend's to decide.
  // The UI must never arm itself from the state name alone.
  it("is disabled unless the backend says can_authorize", () => {
    const { rerender } = render(
      <StateBanner
        state="AWAITING_AUTHORIZATION"
        mission={makeMission({
          state: "AWAITING_AUTHORIZATION",
          can_authorize: false,
        })}
        onAuthorize={vi.fn()}
      />,
    );
    expect(screen.getByRole("button")).toBeDisabled();

    rerender(
      <StateBanner
        state="AWAITING_AUTHORIZATION"
        mission={makeMission({
          state: "AWAITING_AUTHORIZATION",
          can_authorize: true,
        })}
        onAuthorize={vi.fn()}
      />,
    );
    expect(screen.getByRole("button")).toBeEnabled();
  });

  it("is disabled when there is no mission at all", () => {
    render(<StateBanner state="SEARCHING" mission={null} onAuthorize={vi.fn()} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("calls onAuthorize when armed and clicked", () => {
    const onAuthorize = vi.fn();
    render(
      <StateBanner
        state="AWAITING_AUTHORIZATION"
        mission={makeMission({ can_authorize: true })}
        onAuthorize={onAuthorize}
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onAuthorize).toHaveBeenCalledTimes(1);
  });

  it("does not fire when disabled", () => {
    const onAuthorize = vi.fn();
    render(
      <StateBanner
        state="TRACKING"
        mission={makeMission({ can_authorize: false })}
        onAuthorize={onAuthorize}
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onAuthorize).not.toHaveBeenCalled();
  });

  it.each(["AUTHORIZED", "ACTUATED"] as const)(
    "reads 'Authorized' once in %s",
    (state) => {
      render(
        <StateBanner
          state={state}
          mission={makeMission({ state })}
          onAuthorize={vi.fn()}
        />,
      );
      expect(screen.getByRole("button")).toHaveTextContent("Authorized");
    },
  );

  it("reads 'Authorize' before the engagement is authorized", () => {
    render(
      <StateBanner
        state="FOLLOWING"
        mission={makeMission()}
        onAuthorize={vi.fn()}
      />,
    );
    expect(screen.getByRole("button")).toHaveTextContent("Authorize");
  });

  it("marks only AWAITING_AUTHORIZATION as urgent", () => {
    const { container, rerender } = render(
      <StateBanner
        state="AWAITING_AUTHORIZATION"
        mission={makeMission()}
        onAuthorize={vi.fn()}
      />,
    );
    expect(container.querySelector(".banner")).toHaveClass("is-urgent");

    rerender(
      <StateBanner
        state="TRACKING"
        mission={makeMission()}
        onAuthorize={vi.fn()}
      />,
    );
    expect(container.querySelector(".banner")).not.toHaveClass("is-urgent");
  });

  it("passes the state colour and progress through as CSS custom properties", () => {
    const { container } = render(
      <StateBanner
        state="THREAT_CONFIRMED"
        mission={makeMission({ progress: 0.75 })}
        onAuthorize={vi.fn()}
      />,
    );
    const banner = container.querySelector(".banner") as HTMLElement;
    expect(banner.style.getPropertyValue("--state-color")).toBe("var(--threat)");
    expect(banner.style.getPropertyValue("--progress")).toBe("0.75");
  });

  it("defaults progress to 0 with no mission", () => {
    const { container } = render(
      <StateBanner state="SEARCHING" mission={null} onAuthorize={vi.fn()} />,
    );
    const banner = container.querySelector(".banner") as HTMLElement;
    expect(banner.style.getPropertyValue("--progress")).toBe("0");
  });
});
