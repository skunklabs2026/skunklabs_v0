import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useSource } from "./useSource";
import { ApiError } from "../api/client";
import type { SourceStatus } from "../types";

// vi.mock is hoisted above module scope, so the doubles have to be too.
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

const STATUS = {
  kind: "video",
  active_video: "clip.mp4",
} as unknown as SourceStatus;

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.fetchStatus.mockResolvedValue(STATUS);
  api.selectVideo.mockResolvedValue({ detail: "Loaded clip.mp4" });
  api.selectDetector.mockResolvedValue({ detail: "Detector is yolo" });
  api.setThreshold.mockResolvedValue({});
  api.selectCamera.mockResolvedValue({});
  api.removeUpload.mockResolvedValue({});
  api.uploadVideo.mockResolvedValue({ detail: "Stored" });
});

afterEach(() => vi.useRealTimers());

describe("initial load", () => {
  it("fetches status on mount", async () => {
    const { result } = renderHook(() => useSource());
    await waitFor(() => expect(result.current.status).toEqual(STATUS));
  });

  it("swallows a failed status read — telemetry already reports connectivity", async () => {
    api.fetchStatus.mockRejectedValue(new ApiError("offline", 0));
    const { result } = renderHook(() => useSource());
    await waitFor(() => expect(api.fetchStatus).toHaveBeenCalled());
    expect(result.current.status).toBeNull();
    expect(result.current.error).toBeNull();
  });
});

describe("mutations", () => {
  it.each([
    [
      "selectVideo",
      (r: ReturnType<typeof useSource>) => r.selectVideo("/clips/a.mp4"),
      "selectVideo",
    ],
    [
      "selectDetector",
      (r: ReturnType<typeof useSource>) => r.selectDetector("yolo"),
      "selectDetector",
    ],
    [
      "setThreshold",
      (r: ReturnType<typeof useSource>) => r.setThreshold(0.7),
      "setThreshold",
    ],
    [
      "selectCamera",
      (r: ReturnType<typeof useSource>) => r.selectCamera(1),
      "selectCamera",
    ],
    [
      "removeUpload",
      (r: ReturnType<typeof useSource>) => r.removeUpload("a.mp4"),
      "removeUpload",
    ],
  ] as const)(
    "%s calls the api and reports success",
    async (_name, call, apiName) => {
      const { result } = renderHook(() => useSource());
      await waitFor(() => expect(result.current.status).not.toBeNull());

      let ok: boolean | undefined;
      await act(async () => {
        ok = await call(result.current);
      });
      expect(ok).toBe(true);
      expect(api[apiName]).toHaveBeenCalled();
      expect(result.current.error).toBeNull();
      expect(result.current.busy).toBe(false);
    },
  );

  it("defaults the camera index to 0", async () => {
    const { result } = renderHook(() => useSource());
    await act(async () => void (await result.current.selectCamera()));
    expect(api.selectCamera).toHaveBeenCalledWith(0);
  });

  it("prefers the backend's detail over the generic fallback message", async () => {
    const { result } = renderHook(() => useSource());
    await act(async () => void (await result.current.selectVideo("/a.mp4")));
    expect(result.current.message).toBe("Loaded clip.mp4");
  });

  it("falls back to a generic message when the backend sends no detail", async () => {
    api.selectVideo.mockResolvedValue({});
    const { result } = renderHook(() => useSource());
    await act(async () => void (await result.current.selectVideo("/a.mp4")));
    expect(result.current.message).toBe("Source loaded.");
  });

  it("surfaces the backend's message on failure and returns false", async () => {
    api.selectVideo.mockRejectedValue(new ApiError("Not a video file", 400));
    const { result } = renderHook(() => useSource());

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.selectVideo("/a.txt");
    });
    expect(ok).toBe(false);
    expect(result.current.error).toBe("Not a video file");
    expect(result.current.message).toBeNull();
    expect(result.current.busy).toBe(false);
  });

  it("stringifies a non-Error rejection rather than showing [object Object]", async () => {
    api.selectVideo.mockRejectedValue("plain string failure");
    const { result } = renderHook(() => useSource());
    await act(async () => void (await result.current.selectVideo("/a.mp4")));
    expect(result.current.error).toBe("plain string failure");
  });

  it("clears a previous error when the next command starts", async () => {
    api.selectVideo.mockRejectedValueOnce(new ApiError("boom", 400));
    const { result } = renderHook(() => useSource());
    await act(async () => void (await result.current.selectVideo("/a.mp4")));
    expect(result.current.error).toBe("boom");

    await act(async () => void (await result.current.selectVideo("/b.mp4")));
    expect(result.current.error).toBeNull();
  });
});

// Source swaps are applied by the pipeline worker between frames, so an
// immediate re-read can still return the old value.
describe("settle refresh", () => {
  it("refreshes again 1200ms after a mutation", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useSource());
    await act(async () => {
      await Promise.resolve();
    });
    const afterMount = api.fetchStatus.mock.calls.length;

    await act(async () => void (await result.current.selectDetector("yolo")));
    const afterMutation = api.fetchStatus.mock.calls.length;
    expect(afterMutation).toBe(afterMount + 1);

    await act(async () => {
      vi.advanceTimersByTime(1200);
      await Promise.resolve();
    });
    expect(api.fetchStatus.mock.calls.length).toBe(afterMutation + 1);
  });

  it("cancels a pending settle timer on unmount", async () => {
    vi.useFakeTimers();
    const { result, unmount } = renderHook(() => useSource());
    await act(async () => void (await result.current.selectDetector("yolo")));
    const before = api.fetchStatus.mock.calls.length;

    unmount();
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });
    expect(api.fetchStatus.mock.calls.length).toBe(before);
  });
});

describe("upload", () => {
  it("reports progress and clears it when finished", async () => {
    const seen: (number | null)[] = [];
    api.uploadVideo.mockImplementation(
      async (_file: File, onProgress: (p: number) => void) => {
        onProgress(40);
        onProgress(100);
        return { detail: "Stored" };
      },
    );

    const { result } = renderHook(() => useSource());
    await waitFor(() => expect(result.current.status).not.toBeNull());
    seen.push(result.current.uploadPercent);

    const file = new File(["x"], "clip.mp4");
    await act(async () => void (await result.current.upload(file)));

    expect(seen[0]).toBeNull();
    // Cleared once the request settles, whatever the last percent was.
    expect(result.current.uploadPercent).toBeNull();
    expect(result.current.message).toBe("Stored");
  });

  it("clears the progress indicator even when the upload fails", async () => {
    api.uploadVideo.mockRejectedValue(new ApiError("File exceeds the limit", 413));
    const { result } = renderHook(() => useSource());

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.upload(new File(["x"], "big.mp4"));
    });
    expect(ok).toBe(false);
    expect(result.current.uploadPercent).toBeNull();
    expect(result.current.error).toBe("File exceeds the limit");
  });
});
