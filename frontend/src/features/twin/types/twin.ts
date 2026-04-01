export interface TwinProfile {
  session_id: string;
  summary: string;
  memory_count: number;
  latest_topics: string[];
  twin_status: "training" | "deployed";
}

export interface SimulationRequest {
  session_id: string;
  scenario: string;
  debug?: boolean;
}

export interface SimulationDebugMemory {
  id: string;
  text: string;
  context: string;
  relevance_rank: number | null;
}

export interface SimulationDebug {
  used_traits: string[];
  used_memories: SimulationDebugMemory[];
  profile_snapshot: Record<string, string[]>;
}

export interface SimulationResponse {
  decision: string;
  reasoning: string;
  debug?: SimulationDebug;
}

export interface TwinLifecycleTransitionResponse {
  message: string;
  new_session_id: string | null;
  previous_session_archived: boolean;
}
