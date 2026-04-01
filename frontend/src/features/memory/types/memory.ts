export interface MemoryItem {
  id: string;
  role: string;
  text: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MemoryListResponse {
  session_id: string;
  count: number;
  items: MemoryItem[];
}
