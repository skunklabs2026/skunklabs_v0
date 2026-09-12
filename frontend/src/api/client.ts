/**
 * The HTTP transport.
 *
 * One job: turn a request into either parsed data or an `ApiError` carrying
 * a message worth showing an operator. The backend answers failures with
 * `{"detail": "..."}` written for exactly that purpose, so the client's main
 * responsibility is not to lose it - a bare "Request failed (400)" in front
 * of someone mid-demo is a bug, not an error message.
 */

/** A failed request, with the backend's explanation preserved. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** True when the failure means "the backend is not reachable". */
export function isOffline(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0;
}

interface ErrorBody {
  detail?: string | { msg?: string }[];
}

/** Pull an operator-readable message out of a FastAPI error body. */
function messageFrom(body: ErrorBody, status: number): string {
  const { detail } = body;
  if (typeof detail === "string" && detail) return detail;
  // Pydantic validation errors arrive as a list of issues; the first one is
  // the useful one.
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return `Request failed (${status})`;
}

async function parse<T>(response: Response): Promise<T> {
  // 204 and empty bodies are valid; JSON.parse on "" would throw.
  const text = await response.text();
  const body = text ? ((JSON.parse(text) as unknown) ?? {}) : {};

  if (!response.ok) {
    throw new ApiError(
      messageFrom(body as ErrorBody, response.status),
      response.status,
    );
  }
  return body as T;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    // A network-level failure has no status. Status 0 marks it as such so
    // callers can distinguish "backend is down" from "backend said no".
    throw new ApiError("Cannot reach the backend. Is it running?", 0);
  }
  return parse<T>(response);
}

export function get<T>(url: string): Promise<T> {
  return request<T>(url);
}

export function post<T>(url: string, body?: unknown): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function del<T>(url: string): Promise<T> {
  return request<T>(url, { method: "DELETE" });
}
