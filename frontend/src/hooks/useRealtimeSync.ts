import { useEffect, useRef, useState } from "react";

import { getBackendBaseUrl } from "@/api/client";

type RealtimeEventType = "profile_update" | "memory_update" | "simulation_result" | "error";

interface RealtimeEventPayload {
  type: RealtimeEventType;
  data: Record<string, unknown>;
}

interface UseRealtimeSyncOptions {
  sessionId: string;
  onEvent: (event: RealtimeEventPayload) => void;
  pollFallback: () => Promise<void>;
}

function getWebSocketUrl(sessionId: string): string {
  const backendBase = getBackendBaseUrl();
  const wsBase = backendBase.replace(/^http/, "ws");
  return `${wsBase}/ws/${encodeURIComponent(sessionId)}`;
}

export function useRealtimeSync({ sessionId, onEvent, pollFallback }: UseRealtimeSyncOptions) {
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const pollingTimerRef = useRef<number | null>(null);
  const onEventRef = useRef(onEvent);
  const pollFallbackRef = useRef(pollFallback);
  const [isRealtimeConnected, setIsRealtimeConnected] = useState(false);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    pollFallbackRef.current = pollFallback;
  }, [pollFallback]);

  useEffect(() => {
    let disposed = false;

    async function startPollingFallback(): Promise<void> {
      if (pollingTimerRef.current !== null) {
        return;
      }
      pollingTimerRef.current = window.setInterval(() => {
        void pollFallbackRef.current();
      }, 3000);
      await pollFallbackRef.current();
    }

    function stopPollingFallback(): void {
      if (pollingTimerRef.current !== null) {
        window.clearInterval(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    }

    function scheduleReconnect(): void {
      if (disposed || reconnectTimerRef.current !== null) {
        return;
      }
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, 2000);
    }

    function connect(): void {
      if (disposed || !sessionId) {
        return;
      }

      try {
        const socket = new WebSocket(getWebSocketUrl(sessionId));
        socketRef.current = socket;

        socket.onopen = () => {
          setIsRealtimeConnected(true);
          stopPollingFallback();
        };

        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data) as RealtimeEventPayload;
            if (!payload || typeof payload.type !== "string") {
              return;
            }
            onEventRef.current(payload);
          } catch {
            // Ignore malformed events and continue streaming.
          }
        };

        socket.onerror = () => {
          setIsRealtimeConnected(false);
          void startPollingFallback();
        };

        socket.onclose = () => {
          setIsRealtimeConnected(false);
          void startPollingFallback();
          scheduleReconnect();
        };
      } catch {
        setIsRealtimeConnected(false);
        void startPollingFallback();
        scheduleReconnect();
      }
    }

    connect();

    return () => {
      disposed = true;
      setIsRealtimeConnected(false);
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (pollingTimerRef.current !== null) {
        window.clearInterval(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [sessionId]);

  return { isRealtimeConnected };
}
