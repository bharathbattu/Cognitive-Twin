import { useEffect, useState } from "react";

import { fetchSessionMemory } from "@/api/twinApi";
import SectionCard from "@/components/common/SectionCard";
import type { MemoryListResponse } from "@/features/memory/types/memory";

interface MemoryListProps {
  sessionId: string;
  refreshKey?: number;
}

function MemoryList({ sessionId, refreshKey = 0 }: MemoryListProps) {
  const [memory, setMemory] = useState<MemoryListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setIsLoading(true);

    fetchSessionMemory(sessionId)
      .then((data) => {
        if (active) {
          setMemory(data);
          setError(null);
        }
      })
      .catch((loadError) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "Unable to load memory.");
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [refreshKey, sessionId]);

  return (
    <SectionCard title="Persistent Memory" eyebrow="JSON + FAISS">
      {error ? <p className="text-sm text-rose-600">{error}</p> : null}
      {isLoading ? <p className="mb-3 text-sm text-slate-500">Loading memory...</p> : null}
      <ul className="space-y-3">
        {(memory?.items ?? []).length > 0 ? (
          memory?.items.map((item) => (
            <li key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
                  {item.role}
                </span>
                <span className="text-xs text-slate-500">{new Date(item.created_at).toLocaleString()}</span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-700">{item.text}</p>
            </li>
          ))
        ) : (
          <li className="rounded-2xl border border-dashed border-slate-300 bg-white p-5 text-sm text-slate-500">
            No stored memory yet. Send a chat message or create memory items from the backend.
          </li>
        )}
      </ul>
    </SectionCard>
  );
}

export default MemoryList;
