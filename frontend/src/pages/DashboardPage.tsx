import { useCallback, useEffect, useState } from "react";

import { fetchBackendHealth } from "@/api/twinApi";
import AppShell from "@/components/layout/AppShell";
import ChatPanel from "@/features/chat/components/ChatPanel";
import MemoryList from "@/features/memory/components/MemoryList";
import SimulationPanel from "@/features/twin/components/SimulationPanel";
import TwinProfileCard from "@/features/twin/components/TwinProfileCard";
import { useRealtimeSync } from "@/hooks/useRealtimeSync";
import useSessionId from "@/hooks/useSessionId";

function DashboardPage() {
  const { sessionId, setSessionId } = useSessionId();
  const [refreshKey, setRefreshKey] = useState(0);
  const [backendStatus, setBackendStatus] = useState<"connected" | "down">("down");

  const handleDataRefresh = useCallback((): void => {
    setRefreshKey((current) => current + 1);
  }, []);

  const refreshFromBackend = useCallback(async () => {
    try {
      await fetchBackendHealth();
      setBackendStatus("connected");
      handleDataRefresh();
    } catch {
      setBackendStatus("down");
    }
  }, [handleDataRefresh]);

  const handleRealtimeEvent = useCallback(() => {
    setBackendStatus("connected");
    handleDataRefresh();
  }, [handleDataRefresh]);

  useEffect(() => {
    void refreshFromBackend();
  }, [refreshFromBackend, sessionId]);

  const { isRealtimeConnected } = useRealtimeSync({
    sessionId,
    onEvent: handleRealtimeEvent,
    pollFallback: refreshFromBackend
  });

  function handleSessionTransition(newSessionId: string): void {
    setSessionId(newSessionId);
    setRefreshKey((current) => current + 1);
  }

  return (
    <AppShell
      title="Cognitive Twin"
      subtitle="A full-stack foundation for memory-aware AI experiences with FastAPI, React, OpenRouter, FAISS, and JSON persistence."
      backendStatus={backendStatus}
      realtimeStatus={isRealtimeConnected ? "connected" : "polling"}
    >
      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          <ChatPanel sessionId={sessionId} onComplete={handleDataRefresh} onSessionTransition={handleSessionTransition} />
          <SimulationPanel key={`simulation-${sessionId}`} sessionId={sessionId} onComplete={handleDataRefresh} />
          <MemoryList key={`memory-${sessionId}`} sessionId={sessionId} refreshKey={refreshKey} />
        </div>
        <div className="space-y-6">
          <TwinProfileCard key={`profile-${sessionId}`} sessionId={sessionId} refreshKey={refreshKey} />
        </div>
      </div>
    </AppShell>
  );
}

export default DashboardPage;
