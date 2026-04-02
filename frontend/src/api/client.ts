import { API_URL, BACKEND_URL, buildApiUrl } from "@/config/api";

const REQUEST_TIMEOUT_MS = 10_000;
const NETWORK_RETRIES = 1;

export interface ApiClientOptions extends RequestInit {
  timeoutMs?: number;
  retries?: number;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
}

export function getApiBaseUrl(): string {
  return API_URL;
}

export function getBackendBaseUrl(): string {
  return BACKEND_URL;
}

function normalizeMethod(method?: string): string {
  return (method ?? "GET").toUpperCase();
}

function formatBodyForLog(body: BodyInit | null | undefined): string {
  if (body == null) {
    return "<empty>";
  }
  if (typeof body === "string") {
    return body;
  }
  if (body instanceof FormData) {
    return "<form-data>";
  }
  if (body instanceof URLSearchParams) {
    return body.toString();
  }
  return "<binary>";
}

function withDefaultHeaders(init: RequestInit | undefined, method: string): HeadersInit {
  const baseHeaders = init?.headers ?? {};
  if (init?.body == null) {
    return baseHeaders;
  }

  const headers = new Headers(baseHeaders);
  const hasContentType = headers.has("Content-Type");
  const canSetJsonHeader = typeof init.body === "string" && method !== "GET" && method !== "HEAD";

  if (!hasContentType && canSetJsonHeader) {
    headers.set("Content-Type", "application/json");
  }

  return headers;
}

async function fetchWithTimeout(url: string, timeoutMs: number, method: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...init,
      method,
      signal: controller.signal,
      headers: withDefaultHeaders(init, method)
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

function normalizeClientError(error: Error, timeoutMs: number): Error {
  const timeoutSeconds = Math.max(1, Math.round(timeoutMs / 1000));
  const isAbortError =
    error.name === "AbortError" ||
    error.name === "TimeoutError" ||
    /signal is aborted|aborted|timeout|timed out/i.test(error.message);

  if (isAbortError) {
    return new Error(`Request timed out after ${timeoutSeconds}s. Please try again.`);
  }

  if (/failed to fetch/i.test(error.message)) {
    return new Error("Unable to reach the backend. It may be down or blocked by a CORS origin mismatch.");
  }

  return error;
}

async function parseResponsePayload(response: Response): Promise<unknown> {
  const raw = await response.text();
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    throw new Error("Invalid JSON response from backend.");
  }
}

export async function apiClient<T>(path: string, options?: ApiClientOptions): Promise<T> {
  const { timeoutMs = REQUEST_TIMEOUT_MS, retries = NETWORK_RETRIES, ...init } = options ?? {};
  const endpoint = path.startsWith("http") ? path : buildApiUrl(path);
  const method = normalizeMethod(init.method);

  if (!endpoint.startsWith("http")) {
    throw new Error("VITE_API_URL is not configured. Set it in frontend environment variables.");
  }

  console.log("API Request:", {
    url: endpoint,
    method,
    payload: formatBodyForLog(init.body)
  });

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const response = await fetchWithTimeout(endpoint, timeoutMs, method, init);
      const payload = await parseResponsePayload(response);

      if (!response.ok) {
        if (response.status === 405) {
          throw new Error(`Method mismatch (${method}) for endpoint ${endpoint}.`);
        }

        const errorMessage =
          typeof payload === "object" && payload && "error" in payload && typeof (payload as { error?: unknown }).error === "string"
            ? (payload as { error: string }).error
            : `Request failed: ${response.status} (${method} ${endpoint})`;
        throw new Error(errorMessage);
      }

      if (
        typeof payload === "object" &&
        payload !== null &&
        "success" in payload &&
        "data" in payload
      ) {
        const envelope = payload as ApiEnvelope<T>;
        if (!envelope.success || envelope.data === null) {
          throw new Error(envelope.error || "API request failed.");
        }
        return envelope.data;
      }

      return payload as T;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Unknown API client error.");
      lastError = normalizeClientError(lastError, timeoutMs);
      const isAbort = lastError.name === "AbortError" || /timed out/i.test(lastError.message);
      const isNetwork =
        /network|failed to fetch|unable to reach the backend|cors/i.test(lastError.message) || isAbort;
      if (!isNetwork || attempt >= retries) {
        console.error("API Error:", lastError);
        throw lastError;
      }
    }
  }

  throw lastError ?? new Error("Unknown API client error.");
}
