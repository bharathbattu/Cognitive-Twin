import { useCallback, useState } from "react";

const SESSION_STORAGE_KEY = "cognitive_twin_session_id";
const DEFAULT_SESSION_ID = "default-session";

function resolveInitialSessionId(): string {
  if (typeof window === "undefined") {
    return DEFAULT_SESSION_ID;
  }

  const stored = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (stored && stored.trim()) {
    return stored;
  }
  return DEFAULT_SESSION_ID;
}

function useSessionId() {
  const [sessionId, setSessionIdState] = useState<string>(resolveInitialSessionId);

  const setSessionId = useCallback((nextSessionId: string) => {
    const normalized = nextSessionId.trim();
    if (!normalized) {
      return;
    }
    setSessionIdState(normalized);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SESSION_STORAGE_KEY, normalized);
    }
  }, []);

  return { sessionId, setSessionId };
}

export default useSessionId;
