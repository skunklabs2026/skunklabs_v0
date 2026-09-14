import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SetupScreen } from "./SetupScreen";
import {
  makeTelemetry,
  makeSystem,
  makeDetection,
  makeSourceStatus,
  makeVideo,
} from "../test/factories";

const api = vi.hoisted(() => ({
  fetchStatus: vi.fn(),
  selectVideo: vi.fn(),
  selectDetector: vi.fn(),
  setThreshold: vi.fn(),
  selectCamera: vi.fn(),
  removeUpload: vi.fn(),
  uploadVideo: vi.fn(),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, sourceApi: api };
});

/** Telemetry with frames genuinely flowing — the precondition for BEGIN. */
const liveTelemetry = makeTelemetry({
  system: makeSystem({ sensor_online: true, frame_index: 120 }),
  detection: makeDetection(),
});

/** The component's own props, so a fixture cannot drift from it. */
type Props = ComponentProps<typeof SetupScreen>;

const base: Props = {
  telemetry: liveTelemetry,
  connected: true,
  onBegin: vi.fn(),
};

async function setup(props: Partial<Props> = {}) {
  const result = render(<SetupScreen {...base} {...props} />);
  await waitFor(() => expect(api.fetchStatus).toHaveBeenCalled());
  return result;
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.fetchStatus.mockResolvedValue(makeSourceStatus());
  api.selectVideo.mockResolvedValue({ detail: "Loaded." });
  api.selectDetector.mockResolvedValue({ detail: "Detector changed." });
  api.setThreshold.mockResolvedValue({});
  api.selectCamera.mockResolvedValue({});
  api.removeUpload.mockResolvedValue({});
  api.uploadVideo.mockResolvedValue({});
});

describe("header", () => {
  it("names the screen and reports the backend link", async () => {
    await setup();
    expect(screen.getByText("Canister 01 · Mission Setup")).toBeInTheDocument();
    expect(screen.getByText("Backend online")).toBeInTheDocument();
  });

  it("says connecting while the link is down", async () => {
    await setup({ connected: false });
    expect(screen.getByText("Connecting")).toBeInTheDocument();
  });
});

describe("the three steps", () => {
  it("presents them in the order the work happens", async () => {
    const { container } = await setup();
    const steps = [...container.querySelectorAll(".setup-step")].map(
      (h) => h.textContent,
    );
    expect(steps).toEqual([
      "1 Load footage",
      "2 Choose a detector",
      "3 Confirm it is tracking",
    ]);
  });
});

describe("source selection", () => {
  it("lists the library from backend status", async () => {
    api.fetchStatus.mockResolvedValue(
      makeSourceStatus({ videos: [makeVideo({ name: "approach.mp4" })] }),
    );
    await setup();
    await waitFor(() =>
      expect(screen.getByText("approach.mp4")).toBeInTheDocument(),
    );
  });

  it("selects a clip", async () => {
    const video = makeVideo({ name: "approach.mp4" });
    api.fetchStatus.mockResolvedValue(makeSourceStatus({ videos: [video] }));
    await setup();

    await waitFor(() =>
      expect(screen.getByText("approach.mp4")).toBeInTheDocument(),
    );
    await act(async () => {
      fireEvent.click(screen.getByText("approach.mp4"));
    });
    expect(api.selectVideo).toHaveBeenCalledWith(video);
  });

  it("switches to the camera", async () => {
    await setup();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Use camera instead" }));
    });
    expect(api.selectCamera).toHaveBeenCalledWith(0);
  });

  it("uploads a dropped file", async () => {
    await setup();
    const file = new File(["x"], "clip.mp4", { type: "video/mp4" });
    await act(async () => {
      fireEvent.drop(screen.getByRole("button", { name: "Upload a video" }), {
        dataTransfer: { files: [file] },
      });
    });
    expect(api.uploadVideo).toHaveBeenCalledWith(file, expect.any(Function));
  });

  it("names a camera source rather than showing a path", async () => {
    api.fetchStatus.mockResolvedValue(
      makeSourceStatus({ video_source: "camera", camera_index: 2 }),
    );
    await setup();
    await waitFor(() => expect(screen.getByText("Camera 2")).toBeInTheDocument());
  });

  it("shows only the filename of a clip, not its whole path", async () => {
    api.fetchStatus.mockResolvedValue(
      makeSourceStatus({ active_video: "/long/path/to/approach.mp4" }),
    );
    await setup();
    await waitFor(() =>
      expect(screen.getByText("approach.mp4")).toBeInTheDocument(),
    );
  });
});

describe("detector", () => {
  it("changes detector", async () => {
    await setup();
    await act(async () => {
      fireEvent.click(screen.getByText("yolo"));
    });
    expect(api.selectDetector).toHaveBeenCalledWith("yolo");
  });

  // Telemetry is authoritative about what is actually running; source status
  // can lag a frame while the worker applies the swap.
  it("shows the detector telemetry reports, not the one status claims", async () => {
    api.fetchStatus.mockResolvedValue(makeSourceStatus({ detector: "motion" }));
    const { container } = await setup({
      telemetry: makeTelemetry({
        system: makeSystem({ detector: "yolo", frame_index: 5 }),
      }),
    });
    await waitFor(() => {
      const on = container.querySelector(".detector-card.is-on");
      expect(on).toHaveTextContent("yolo");
    });
  });

  it("moves the slider immediately, before the POST resolves", async () => {
    await setup();
    const slider = screen.getByLabelText("Detection confidence threshold");
    await act(async () => {
      fireEvent.change(slider, { target: { value: "0.75" } });
    });
    expect(api.setThreshold).toHaveBeenCalledWith(0.75);
    expect(screen.getByText("0.75")).toBeInTheDocument();
  });
});

describe("verification and BEGIN", () => {
  it("enables BEGIN once frames are genuinely flowing", async () => {
    await setup();
    expect(screen.getByRole("button", { name: "Begin mission" })).toBeEnabled();
  });

  // Nobody should start a mission against a dead source.
  it("keeps BEGIN disabled before any frame has been processed", async () => {
    await setup({
      telemetry: makeTelemetry({ system: makeSystem({ frame_index: 0 }) }),
    });
    const begin = screen.getByRole("button", { name: "Load a source to continue" });
    expect(begin).toBeDisabled();
  });

  it("keeps BEGIN disabled while the sensor is offline", async () => {
    await setup({
      telemetry: makeTelemetry({
        system: makeSystem({ sensor_online: false, frame_index: 500 }),
      }),
    });
    expect(
      screen.getByRole("button", { name: "Load a source to continue" }),
    ).toBeDisabled();
  });

  it("keeps BEGIN disabled with no telemetry at all", async () => {
    await setup({ telemetry: null });
    expect(
      screen.getByRole("button", { name: "Load a source to continue" }),
    ).toBeDisabled();
  });

  it("begins the mission", async () => {
    const onBegin = vi.fn();
    await setup({ onBegin });
    fireEvent.click(screen.getByRole("button", { name: "Begin mission" }));
    expect(onBegin).toHaveBeenCalled();
  });

  it("shows the live preview once frames flow", async () => {
    const { container } = await setup();
    expect(screen.getByAltText("Source preview")).toHaveAttribute(
      "src",
      "/api/video",
    );
    expect(
      (container.querySelector(".preview-frame") as HTMLElement).style.aspectRatio,
    ).toBe("960 / 540");
  });

  it("waits for frames instead of showing a dead preview", async () => {
    await setup({
      telemetry: makeTelemetry({ system: makeSystem({ frame_index: 0 }) }),
    });
    expect(screen.getByText("Waiting for frames…")).toBeInTheDocument();
    expect(screen.queryByAltText("Source preview")).not.toBeInTheDocument();
  });

  it("says the backend is offline rather than waiting for frames", async () => {
    await setup({
      connected: false,
      telemetry: makeTelemetry({ system: makeSystem({ frame_index: 0 }) }),
    });
    expect(screen.getByText("Backend offline")).toBeInTheDocument();
  });
});

describe("feedback", () => {
  it("shows the backend's success message", async () => {
    await setup();
    await act(async () => {
      fireEvent.click(screen.getByText("yolo"));
    });
    await waitFor(() =>
      expect(screen.getByText("Detector changed.")).toBeInTheDocument(),
    );
  });

  it("shows the backend's failure message", async () => {
    api.selectDetector.mockRejectedValue(new Error("YOLO weights not found"));
    const { container } = await setup();
    await act(async () => {
      fireEvent.click(screen.getByText("yolo"));
    });
    await waitFor(() => {
      expect(screen.getByText("YOLO weights not found")).toBeInTheDocument();
      expect(container.querySelector(".note.is-bad")).toBeInTheDocument();
    });
  });
});
