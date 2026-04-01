const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
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
  return API_BASE_URL;
}

export function getBackendBaseUrl(): string {
  return API_BASE_URL.replace(/\/api\/v1\/?$/, "");
}

async function fetchWithTimeout(url: string, timeoutMs: number, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {})
      }
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
  const endpoint = path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const response = await fetchWithTimeout(endpoint, timeoutMs, init);
      const payload = await parseResponsePayload(response);

      if (!response.ok) {
        const errorMessage =
          typeof payload === "object" && payload && "error" in payload && typeof (payload as { error?: unknown }).error === "string"
            ? (payload as { error: string }).error
            : `Request failed: ${response.status}`;
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
      const isNetwork = /network|failed to fetch/i.test(lastError.message) || isAbort;
      if (!isNetwork || attempt >= retries) {
        console.error("API Error:", lastError);
        throw lastError;
      }
    }
  }

  throw lastError ?? new Error("Unknown API client error.");
}
