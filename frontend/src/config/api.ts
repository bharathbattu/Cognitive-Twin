const rawApiUrl = import.meta.env.VITE_API_URL?.trim() ?? "";

if (!rawApiUrl) {
  console.error("Missing VITE_API_URL. Configure it to enable API and websocket connectivity.");
}

function removeTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

export const API_URL = removeTrailingSlash(rawApiUrl);
export const WS_URL = API_URL.replace("https", "wss").replace("http", "ws");

export function buildApiUrl(path: string): string {
  if (!API_URL) {
    throw new Error("VITE_API_URL is not configured.");
  }
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export function buildWsUrl(path: string): string {
  if (!WS_URL) {
    throw new Error("VITE_API_URL is not configured.");
  }
  return `${WS_URL}${path.startsWith("/") ? path : `/${path}`}`;
}