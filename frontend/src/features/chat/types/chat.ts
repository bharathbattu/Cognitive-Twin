export interface ChatRequest {
  message: string;
  session_id: string;
  top_k?: number;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  model: string;
  memory_hits: Array<{
    id: string;
    text: string;
    role: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }>;
}
