import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import SectionCard from "@/components/common/SectionCard";
import { sendChatMessage } from "@/features/chat/api/chatApi";
import type { ChatResponse } from "@/features/chat/types/chat";
import { transitionTwinLifecycle } from "@/api/twinApi";

interface ChatPanelProps {
  sessionId: string;
  onComplete?: () => void;
  onSessionTransition?: (newSessionId: string) => void;
}

function ChatPanel({ sessionId, onComplete, onSessionTransition }: ChatPanelProps) {
  const [message, setMessage] = useState("");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setMessage("");
    setResponse(null);
    setError(null);
    setNotice(null);
  }, [sessionId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!message.trim()) return;

    setIsSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const nextResponse = await sendChatMessage({
        message,
        session_id: sessionId,
        top_k: 5
      });
      setResponse(nextResponse);

      setMessage("");
      onComplete?.();

      try {
        const transition = await transitionTwinLifecycle(sessionId);
        if (transition.new_session_id) {
          onSessionTransition?.(transition.new_session_id);
        }
      } catch (transitionError) {
        const transitionMessage =
          transitionError instanceof Error
            ? transitionError.message
            : "Session transition could not be completed.";
        setNotice(`Message sent successfully, but lifecycle transition failed: ${transitionMessage}`);
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to reach the backend.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <SectionCard title="Conversation Loop" eyebrow="Chat">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-slate-700">Prompt the twin</span>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            className="min-h-32 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none transition focus:border-emerald-400 focus:bg-white"
            placeholder="Ask Cognitive Twin to reflect, summarize, or respond..."
          />
        </label>

        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "Thinking..." : "Send message"}
        </button>

        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        {notice ? <p className="text-sm text-amber-700">{notice}</p> : null}
      </form>

      <div className="mt-6 space-y-4">
        <div className="rounded-2xl bg-slate-950 p-5 text-slate-100">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Latest Reply</p>
          <p className="mt-3 whitespace-pre-wrap text-base leading-7">
            {response?.reply || "No reply yet. The first successful request will appear here."}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Memory Hits</p>
          <ul className="mt-3 space-y-3">
            {(response?.memory_hits ?? []).length > 0 ? (
              response?.memory_hits.map((item) => (
                <li key={item.id} className="rounded-xl bg-white p-3 text-sm text-slate-700 shadow-sm">
                  {item.text}
                </li>
              ))
            ) : (
              <li className="text-sm text-slate-500">Relevant memories will show here once the store has data.</li>
            )}
          </ul>
        </div>
      </div>
    </SectionCard>
  );
}

export default ChatPanel;
