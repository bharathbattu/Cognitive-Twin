import { apiClient, getBackendBaseUrl } from "@/api/client";
import type { ChatRequest, ChatResponse } from "@/features/chat/types/chat";
import type { MemoryListResponse } from "@/features/memory/types/memory";
import type {
  SimulationRequest,
  SimulationResponse,
  TwinLifecycleTransitionResponse,
  TwinProfile
} from "@/features/twin/types/twin";

const SIMULATION_TIMEOUT_MS = 45_000;

export function sendChatMessage(payload: ChatRequest) {
  return apiClient<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchTwinProfile(sessionId: string): Promise<TwinProfile> {
  const data = await apiClient<TwinProfile>(`/twin/${encodeURIComponent(sessionId)}/profile`);
  const profile: TwinProfile = {
    session_id: data.session_id,
    summary: data.summary,
    memory_count: data.memory_count,
    latest_topics: Array.isArray(data.latest_topics) ? data.latest_topics : [],
    twin_status: data.twin_status === "deployed" ? "deployed" : "training"
  };

  console.log("Profile API response:", profile);
  return profile;
}

export function fetchSessionMemory(sessionId: string) {
  return apiClient<MemoryListResponse>(`/memory/${encodeURIComponent(sessionId)}`);
}

export function simulateTwinScenario(payload: SimulationRequest) {
  return apiClient<SimulationResponse>("/twin/simulate", {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: SIMULATION_TIMEOUT_MS,
    retries: 0
  });
}

export function transitionTwinLifecycle(sessionId: string) {
  return apiClient<TwinLifecycleTransitionResponse>(`/twin/${encodeURIComponent(sessionId)}/lifecycle/transition`, {
    method: "POST"
  });
}

export async function fetchBackendHealth(): Promise<{ status: string }> {
  return apiClient<{ status: string }>(`${getBackendBaseUrl()}/health`);
}
