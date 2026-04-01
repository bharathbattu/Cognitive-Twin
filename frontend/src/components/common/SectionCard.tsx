import type { PropsWithChildren, ReactNode } from "react";

interface SectionCardProps extends PropsWithChildren {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
}

function SectionCard({ title, eyebrow, actions, children }: SectionCardProps) {
  return (
    <section className="rounded-3xl border border-white/70 bg-white/80 p-6 shadow-[0_20px_80px_rgba(15,23,42,0.08)] backdrop-blur">
      <header className="mb-5 flex items-start justify-between gap-4">
        <div>
          {eyebrow ? <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">{eyebrow}</p> : null}
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">{title}</h2>
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}

export default SectionCard;
