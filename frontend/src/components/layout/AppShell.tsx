import type { PropsWithChildren } from "react";

interface AppShellProps extends PropsWithChildren {
  title: string;
  subtitle: string;
  backendStatus?: "connected" | "down";
  realtimeStatus?: "connected" | "polling";
}

function AppShell({ title, subtitle, backendStatus = "down", realtimeStatus = "polling", children }: AppShellProps) {
  return (
    <div className="min-h-screen px-4 py-8 sm:px-6 lg:px-10">
      <div className="mx-auto max-w-7xl">
        <header className="mb-10">
          <p className="text-sm font-semibold uppercase tracking-[0.28em] text-emerald-700">AI Memory System</p>
          <h1 className="mt-3 max-w-3xl text-5xl font-semibold tracking-tight text-slate-950">{title}</h1>
          <p className="mt-4 max-w-2xl text-lg text-slate-600">{subtitle}</p>
          <div className="mt-5 flex flex-wrap gap-3 text-xs font-semibold uppercase tracking-[0.2em]">
            <span
              className={`rounded-full px-3 py-1 ${
                backendStatus === "connected" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-700"
              }`}
            >
              {backendStatus === "connected" ? "Backend Connected" : "Backend Down"}
            </span>
            <span
              className={`rounded-full px-3 py-1 ${
                realtimeStatus === "connected" ? "bg-sky-100 text-sky-800" : "bg-amber-100 text-amber-800"
              }`}
            >
              {realtimeStatus === "connected" ? "Realtime Sync" : "Polling Fallback"}
            </span>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}

export default AppShell;
