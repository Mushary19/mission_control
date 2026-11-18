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
      <div className="w-sidebar shrink-0 border-r border-zinc-200 bg-zinc-50/60">
      <aside className="sticky top-0 flex h-screen flex-col">
        <div className="flex h-bar shrink-0 items-center gap-3 border-b border-zinc-200 px-6">
          <span className="flex size-6 items-center justify-center rounded-md bg-indigo-600 text-white"><ListChecks className="size-4" /></span>
          <span className="text-card font-semibold">Mission Control</span>
        </div>
        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto px-4 pb-4 pt-2">
          {NAV.map((n, i) =>
            "section" in n ? (
              <div key={i} className="mt-6 px-2 pb-1 text-micro font-medium text-zinc-500">{n.section}</div>
            ) : (
              <NavLink
                key={n.to}
                to={n.to}
                end={"end" in n ? n.end : false}
                className={({ isActive }) =>
                  cn("group flex h-10 shrink-0 items-center gap-3 rounded-lg px-2 text-base text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900", isActive && "bg-indigo-50 font-medium text-indigo-700 hover:bg-indigo-50 hover:text-indigo-700")
                }
              >
                <n.icon className="size-[18px] shrink-0 text-zinc-400 group-aria-[current=page]:text-indigo-600" />
                <span className="flex-1">{n.label}</span>
                {n.to === "/feedback" && fb.data?.count ? <span className="text-xs tabular-nums text-zinc-500">{fb.data.count}</span> : null}
              </NavLink>
            ),
          )}
        </nav>
        <div className="border-t border-zinc-200 px-6 py-4 text-micro text-zinc-500">Harbourline Talent · synthetic data · 2–29 Mar 2026</div>
      </aside>
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-bar shrink-0 items-center justify-between gap-4 border-b border-zinc-200 bg-white px-8">
          <p className="flex min-w-0 items-center gap-2 text-xs text-zinc-600">
            <span className="size-2 shrink-0 rounded-full bg-amber-500" />
            <span className="line-clamp-2">
            <strong className="font-medium text-zinc-900">Data from 6 of 12 staff (People team).</strong> Account Managers, IT and Finance not exported.</span>
          </p>
          <label className="flex shrink-0 items-center gap-2 text-xs text-zinc-500">
            Reviewing as
            <Select value={user} onChange={(e) => setUser(e.target.value)} aria-label="Reviewing as">
              {(staff.length ? allStaff : [{ name: user, job_title: "" }]).map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
            </Select>
          </label>
        </header>
        <main className="flex-1 p-8">
          <div className="w-full max-w-content">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
