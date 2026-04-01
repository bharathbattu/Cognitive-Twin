import type { FormEvent } from "react";
import { useState } from "react";

import { simulateTwinScenario } from "@/api/twinApi";
import SectionCard from "@/components/common/SectionCard";
import type { SimulationResponse } from "@/features/twin/types/twin";

interface SimulationPanelProps {
  sessionId: string;
  onComplete?: () => void;
}

function getErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return "Something went wrong while simulating this situation.";
  }

  if (error.message.includes("500")) {
    return "The simulation engine is available but could not complete this run. Try again in a moment.";
  }

  if (error.message.includes("404")) {
    return "The simulation endpoint is not available yet. Check that the backend is running the latest API.";
  }

  if (/timed out/i.test(error.message)) {
    return "The simulation is taking longer than expected. Please try again in a moment.";
  }

  return error.message || "Something went wrong while simulating this situation.";
}

function SimulationPanel({ sessionId, onComplete }: SimulationPanelProps) {
  const [scenario, setScenario] = useState("");
  const [response, setResponse] = useState<SimulationResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debugEnabled, setDebugEnabled] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scenario.trim()) {
      setError("Describe a situation before running the simulation.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const nextResponse = await simulateTwinScenario({
        session_id: sessionId,
        scenario,
        debug: debugEnabled
      });
      setResponse(nextResponse);
      onComplete?.();
    } catch (submitError) {
      setResponse(null);
      setError(getErrorMessage(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  const usedTraits = response?.debug?.used_traits ?? [];
  const usedMemories = response?.debug?.used_memories ?? [];

  return (
    <SectionCard
      title="Simulation Panel"
      eyebrow="Decision Engine"
      actions={
        <label className="flex items-center gap-3 rounded-full border border-slate-200 bg-white/80 px-4 py-2 text-sm text-slate-600 shadow-sm">
          <span>Debug</span>
          <button
            type="button"
            onClick={() => setDebugEnabled((current) => !current)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${
              debugEnabled ? "bg-emerald-500" : "bg-slate-300"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-white shadow transition ${
                debugEnabled ? "translate-x-5" : "translate-x-1"
              }`}
            />
          </button>
        </label>
      }
    >
      <div className="space-y-6">
        <form className="grid gap-4 lg:grid-cols-[1.35fr_0.65fr]" onSubmit={handleSubmit}>
          <label className="block rounded-[2rem] border border-slate-200 bg-slate-50/80 p-5">
            <span className="mb-3 block text-sm font-medium text-slate-700">Scenario Input</span>
            <textarea
              value={scenario}
              onChange={(event) => setScenario(event.target.value)}
              className="min-h-40 w-full resize-none rounded-[1.5rem] border border-slate-200 bg-white px-4 py-3 text-slate-900 outline-none transition focus:border-emerald-400"
              placeholder="Describe a situation to simulate..."
            />
          </label>

          <div className="flex flex-col justify-between rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Simulation Notes</p>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Ask the twin to model how this user would decide in a concrete situation. The stronger the scenario,
                the more grounded the reasoning will be.
              </p>
              <div className="mt-4 rounded-2xl bg-slate-950 p-4 text-slate-100">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Session</p>
                <p className="mt-2 text-sm font-medium">{sessionId}</p>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-6 inline-flex items-center justify-center gap-3 rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                  Simulating...
                </>
              ) : (
                "Run simulation"
              )}
            </button>
          </div>
        </form>

        {error ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-[2rem] bg-slate-950 p-6 text-slate-100">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Decision</p>
            <p className="mt-4 text-xl font-semibold leading-8">
              {response?.decision || "The simulation decision will appear here once you run a scenario."}
            </p>
          </div>

          <div className="rounded-[2rem] border border-slate-200 bg-slate-50/80 p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Reasoning</p>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-700">
              {response?.reasoning ||
                "The panel will explain why the twin reached its decision, grounded in profile traits and memory."}
            </p>
          </div>
        </div>

        {debugEnabled && response?.debug ? (
          <div className="rounded-[2rem] border border-emerald-200 bg-emerald-50/70 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-emerald-700">Debug Trace</p>
                <h3 className="mt-2 text-lg font-semibold text-slate-900">What the simulator actually used</h3>
              </div>
              <div className="rounded-full bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700 shadow-sm">
                Debug enabled
              </div>
            </div>

            <div className="mt-5 grid gap-4 xl:grid-cols-[0.7fr_1.3fr]">
              <div className="rounded-2xl bg-white p-5 shadow-sm">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Used Traits</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {usedTraits.length > 0 ? (
                    usedTraits.map((trait) => (
                      <span
                        key={trait}
                        className="rounded-full bg-emerald-100 px-3 py-2 text-xs font-semibold text-emerald-800"
                      >
                        {trait}
                      </span>
                    ))
                  ) : (
                    <p className="text-sm text-slate-500">No traits were surfaced in this simulation response.</p>
                  )}
                </div>
              </div>

              <div className="rounded-2xl bg-white p-5 shadow-sm">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Retrieved Memories</p>
                <ul className="mt-4 space-y-3">
                  {usedMemories.length > 0 ? (
                    usedMemories.map((memory) => (
                      <li key={memory.id} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                        <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                          <span>{memory.id}</span>
                          {memory.relevance_rank ? <span>Rank {memory.relevance_rank}</span> : null}
                        </div>
                        <p className="mt-3 text-sm leading-6 text-slate-700">{memory.text}</p>
                        {memory.context ? (
                          <p className="mt-3 text-xs uppercase tracking-[0.18em] text-slate-400">{memory.context}</p>
                        ) : null}
                      </li>
                    ))
                  ) : (
                    <li className="text-sm text-slate-500">No retrieved memories were exposed for this run.</li>
                  )}
                </ul>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </SectionCard>
  );
}

export default SimulationPanel;
