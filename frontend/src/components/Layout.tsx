import { NavLink, Outlet } from "react-router-dom";
import { BookOpen, Briefcase, CircleHelp, LayoutDashboard, LogIn, LogOut, MessageSquareText, Plane, Lightbulb, ListChecks } from "lucide-react";
import { useFeedback, useMeta } from "@/lib/api";
import { useReviewer } from "@/lib/reviewer";
import { Select } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { section: "Processes" },
  { to: "/processes/leave", label: "Leave", icon: Plane },
  { to: "/processes/offboarding", label: "Offboarding", icon: LogOut },
  { to: "/processes/onboarding", label: "Onboarding", icon: LogIn },
  { section: "Review" },
  { to: "/cases", label: "Cases", icon: Briefcase },
  { to: "/insights", label: "Insights", icon: Lightbulb },
  { to: "/questions", label: "Questions", icon: CircleHelp },
  { to: "/feedback", label: "Feedback", icon: MessageSquareText },
  { section: "About" },
  { to: "/how-it-works", label: "How it works", icon: BookOpen },
] as const;

export function Layout() {
  const meta = useMeta();
  const fb = useFeedback();
  const { user, setUser } = useReviewer();
  const staff = meta.data?.coverage.exported.filter((s) => s.job_title !== "Talent Partner") ?? [];
  const allStaff = meta.data?.coverage.exported ?? [];
  return (
    <div className="flex min-h-screen bg-white">
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50/60">
        <div className="flex h-12 items-center gap-2 border-b border-zinc-200 px-4">
          <span className="flex size-6 items-center justify-center rounded-md bg-indigo-600 text-white"><ListChecks className="size-3.5" /></span>
          <span className="text-[13px] font-semibold">Mission Control</span>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {NAV.map((n, i) =>
            "section" in n ? (
              <div key={i} className="px-2 pb-1 pt-4 text-[11px] font-medium uppercase tracking-wide text-zinc-400">{n.section}</div>
            ) : (
              <NavLink
                key={n.to}
                to={n.to}
                end={"end" in n ? n.end : false}
                className={({ isActive }) =>
                  cn("flex h-8 items-center gap-2 rounded-md px-2 text-[13px] text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900", isActive && "bg-white text-zinc-900 font-medium border border-zinc-200")
                }
              >
                <n.icon className="size-4 text-zinc-400" />
                <span className="flex-1">{n.label}</span>
                {n.to === "/feedback" && fb.data?.count ? <span className="text-xs tabular-nums text-zinc-400">{fb.data.count}</span> : null}
              </NavLink>
            ),
          )}
        </nav>
        <div className="border-t border-zinc-200 p-3 text-[11px] leading-snug text-zinc-400">Harbourline Talent · synthetic data · 2–29 Mar 2026</div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-12 items-center justify-between gap-4 border-b border-zinc-200 bg-white px-6">
          <p className="truncate text-xs text-zinc-600">
            <span className="mr-1.5 inline-block size-1.5 -translate-y-px rounded-full bg-amber-500 align-middle" />
            <strong className="font-medium text-zinc-900">Data from 6 of 12 staff (People team).</strong> Account Managers, IT and Finance not exported.
          </p>
          <label className="flex shrink-0 items-center gap-2 text-xs text-zinc-500">
            Reviewing as
            <Select value={user} onChange={(e) => setUser(e.target.value)} aria-label="Reviewing as">
              {(staff.length ? allStaff : [{ name: user, job_title: "" }]).map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
            </Select>
          </label>
        </header>
        <main className="mx-auto w-full max-w-[1200px] flex-1 px-8 py-7">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
