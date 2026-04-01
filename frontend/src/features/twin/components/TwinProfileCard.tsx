import { useEffect, useRef, useState } from "react";

import { fetchTwinProfile } from "@/api/twinApi";
import SectionCard from "@/components/common/SectionCard";
import type { TwinProfile } from "@/features/twin/types/twin";

interface TwinProfileCardProps {
  sessionId: string;
  refreshKey?: number;
}

function TwinProfileCard({ sessionId, refreshKey = 0 }: TwinProfileCardProps) {
  const [profile, setProfile] = useState<TwinProfile | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedSessionRef = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    const isNewSession = loadedSessionRef.current !== sessionId;
    if (isNewSession) {
      setIsLoading(true);
    }

    fetchTwinProfile(sessionId)
      .then((data) => {
        if (active) {
          setProfile(data);
          setError(null);
        }
      })
      .catch((loadError) => {
        if (active) {
          setProfile(null);
          setError(loadError instanceof Error ? loadError.message : "Unable to load profile.");
        }
      })
      .finally(() => {
        if (active) {
          loadedSessionRef.current = sessionId;
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [refreshKey, sessionId]);

  return (
    <SectionCard title="Twin State" eyebrow="Profile">
      {error ? <p className="mb-3 text-sm text-rose-600">{error}</p> : null}
      <div className="grid gap-4 md:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl bg-slate-950 p-5 text-slate-100">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Summary</p>
          <p className="mt-3 text-base leading-7">
            {isLoading ? "Loading profile..." : profile?.summary || "Profile data will appear once the backend is running."}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
          <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Status</p>
            <p className="mt-1 text-sm font-medium text-slate-900">
              {profile?.twin_status === "deployed" ? "Cognitive Twin Active" : "Learning..."}
            </p>
          </div>
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Latest Topics</p>
          <ul className="mt-3 space-y-2">
            {(profile?.latest_topics ?? []).length > 0 ? (
              profile?.latest_topics.map((topic) => (
                <li key={topic} className="text-sm text-slate-700">
                  {topic}
                </li>
              ))
            ) : (
              <li className="text-sm text-slate-500">No topics captured yet.</li>
            )}
          </ul>
          <div className="mt-5 rounded-2xl bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Memory Count</p>
            <p className="mt-2 text-3xl font-semibold text-slate-950">{profile?.memory_count ?? 0}</p>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

export default TwinProfileCard;
