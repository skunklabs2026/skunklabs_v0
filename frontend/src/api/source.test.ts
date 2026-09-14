import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  fetchStatus,
  selectVideo,
  selectCamera,
  selectDetector,
  setThreshold,
  removeUpload,
  uploadVideo,
} from "./source";
import { ApiError } from "./client";
import type { VideoInfo } from "../types";

const fetchMock = vi.fn();

function ok(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response;
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(ok({}));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function bodyOf(call: unknown[]): unknown {
  return JSON.parse((call[1] as RequestInit).body as string);
}

describe("source selection", () => {
  it("fetches status", async () => {
    fetchMock.mockResolvedValue(ok({ kind: "video" }));
    await expect(fetchStatus()).resolves.toEqual({ kind: "video" });
    expect(fetchMock).toHaveBeenCalledWith("/api/source", undefined);
  });

  it("accepts a VideoInfo and sends only its path", async () => {
    const video = {
      path: "/clips/approach.mp4",
      name: "approach.mp4",
    } as VideoInfo;
    await selectVideo(video);
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({
      path: "/clips/approach.mp4",
    });
  });

  it("accepts a bare path string too", async () => {
    await selectVideo("/clips/approach.mp4");
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({
      path: "/clips/approach.mp4",
    });
  });

  it("defaults the camera to index 0", async () => {
    await selectCamera();
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({ camera_index: 0 });
  });

  it("passes an explicit camera index through", async () => {
    await selectCamera(2);
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({ camera_index: 2 });
  });

  it("selects a detector", async () => {
    await selectDetector("yolo");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/source/detector");
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({ detector: "yolo" });
  });

  it("sets a threshold", async () => {
    await setThreshold(0.72);
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({ threshold: 0.72 });
  });

  it("DELETEs an upload by encoded name", async () => {
    await removeUpload("my clip.mp4");
    expect(fetchMock).toHaveBeenCalledWith("/api/source/upload/my%20clip.mp4", {
      method: "DELETE",
    });
  });
});

// uploadVideo uses XMLHttpRequest rather than fetch, purely for upload
// progress, so it needs its own fake.
class FakeXhr {
  static last: FakeXhr;
  status = 200;
  responseText = "{}";
  upload: { onprogress?: (e: ProgressEvent) => void } = {};
  onload?: () => void;
  onerror?: () => void;
  onabort?: () => void;
  opened: [string, string] = ["", ""];
  sent: unknown = null;

  constructor() {
    FakeXhr.last = this;
  }
  open(method: string, url: string) {
    this.opened = [method, url];
  }
  send(body: unknown) {
    this.sent = body;
  }
}

describe("uploadVideo", () => {
  beforeEach(() => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
  });

  function file() {
    return new File(["data"], "clip.mp4", { type: "video/mp4" });
  }

  it("POSTs multipart form data to the upload route", async () => {
    const promise = uploadVideo(file());
    const xhr = FakeXhr.last;
    expect(xhr.opened).toEqual(["POST", "/api/source/upload"]);
    expect(xhr.sent).toBeInstanceOf(FormData);
    xhr.responseText = '{"ok":true}';
    xhr.onload!();
    await expect(promise).resolves.toEqual({ ok: true });
  });

  it("reports progress as a whole percent", async () => {
    const seen: number[] = [];
    const promise = uploadVideo(file(), (p) => seen.push(p));
    const xhr = FakeXhr.last;
    xhr.upload.onprogress!({
      lengthComputable: true,
      loaded: 1,
      total: 3,
    } as ProgressEvent);
    xhr.upload.onprogress!({
      lengthComputable: true,
      loaded: 3,
      total: 3,
    } as ProgressEvent);
    // A stream of unknown length reports nothing rather than NaN%.
    xhr.upload.onprogress!({
      lengthComputable: false,
      loaded: 1,
      total: 0,
    } as ProgressEvent);
    xhr.onload!();
    await promise;
    expect(seen).toEqual([33, 100]);
  });

  it("preserves the backend's detail on a rejected upload", async () => {
    const promise = uploadVideo(file());
    const xhr = FakeXhr.last;
    xhr.status = 413;
    xhr.responseText = '{"detail":"File exceeds the 500 MB limit"}';
    xhr.onload!();
    const error = await promise.catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("File exceeds the 500 MB limit");
    expect((error as ApiError).status).toBe(413);
  });

  it("falls back to a status message when the body is not JSON", async () => {
    const promise = uploadVideo(file());
    const xhr = FakeXhr.last;
    xhr.status = 502;
    xhr.responseText = "<html>Bad Gateway</html>";
    xhr.onload!();
    await expect(promise).rejects.toThrow("Upload failed (502)");
  });

  it("reports a transport failure as offline, not as a server error", async () => {
    const promise = uploadVideo(file());
    FakeXhr.last.onerror!();
    const error = await promise.catch((e: unknown) => e);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toBe(
      "Upload failed — is the backend running?",
    );
  });

  it("reports cancellation distinctly", async () => {
    const promise = uploadVideo(file());
    FakeXhr.last.onabort!();
    await expect(promise).rejects.toThrow("Upload cancelled.");
  });
});
