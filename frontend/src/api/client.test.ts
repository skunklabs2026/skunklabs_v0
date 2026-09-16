import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiError, isOffline, get, post, del } from "./client";

function respond(status: number, body: string): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(body),
  } as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("successful requests", () => {
  it("parses a JSON body", async () => {
    fetchMock.mockResolvedValue(respond(200, '{"state":"SEARCHING"}'));
    await expect(get("/api/telemetry")).resolves.toEqual({
      state: "SEARCHING",
    });
  });

  it("treats an empty body as {} rather than throwing on JSON.parse('')", async () => {
    fetchMock.mockResolvedValue(respond(204, ""));
    await expect(get("/api/telemetry")).resolves.toEqual({});
  });

  it("sends a POST with no body and no content-type when given none", async () => {
    fetchMock.mockResolvedValue(respond(200, "{}"));
    await post("/api/authorize");
    expect(fetchMock).toHaveBeenCalledWith("/api/authorize", {
      method: "POST",
      headers: undefined,
      body: undefined,
    });
  });

  it("serialises a POST body as JSON", async () => {
    fetchMock.mockResolvedValue(respond(200, "{}"));
    await post("/api/source/threshold", { threshold: 0.7 });
    expect(fetchMock).toHaveBeenCalledWith("/api/source/threshold", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: '{"threshold":0.7}',
    });
  });

  it("sends DELETE", async () => {
    fetchMock.mockResolvedValue(respond(200, "{}"));
    await del("/api/source/upload/clip.mp4");
    expect(fetchMock).toHaveBeenCalledWith("/api/source/upload/clip.mp4", {
      method: "DELETE",
    });
  });
});

// The whole reason this module exists: the backend writes `detail` for an
// operator to read, and a bare "Request failed (400)" mid-demo loses it.
describe("error messages", () => {
  it("surfaces FastAPI's string detail", async () => {
    fetchMock.mockResolvedValue(
      respond(400, '{"detail":"Authorization requires AWAITING_AUTHORIZATION"}'),
    );
    await expect(post("/api/authorize")).rejects.toThrow(
      "Authorization requires AWAITING_AUTHORIZATION",
    );
  });

  it("surfaces the first message of a pydantic validation list", async () => {
    fetchMock.mockResolvedValue(
      respond(
        422,
        '{"detail":[{"msg":"path does not exist"},{"msg":"and another"}]}',
      ),
    );
    await expect(post("/api/source/video")).rejects.toThrow("path does not exist");
  });

  it("falls back to a status message when there is no usable detail", async () => {
    fetchMock.mockResolvedValue(respond(500, "{}"));
    await expect(get("/api/telemetry")).rejects.toThrow("Request failed (500)");
  });

  it("carries the status on the ApiError", async () => {
    fetchMock.mockResolvedValue(respond(404, '{"detail":"nope"}'));
    const error = await get("/api/nothing").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).name).toBe("ApiError");
  });
});

describe("isOffline", () => {
  it("distinguishes an unreachable backend from a backend that said no", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const offline = await get("/api/health").catch((e: unknown) => e);
    expect(isOffline(offline)).toBe(true);
    expect((offline as ApiError).status).toBe(0);
    expect((offline as ApiError).message).toBe(
      "Cannot reach the backend. Is it running?",
    );

    fetchMock.mockResolvedValue(respond(400, '{"detail":"said no"}'));
    const refused = await get("/api/health").catch((e: unknown) => e);
    expect(isOffline(refused)).toBe(false);
  });

  it("is false for anything that is not an ApiError", () => {
    expect(isOffline(new Error("boom"))).toBe(false);
    expect(isOffline(null)).toBe(false);
  });
});
