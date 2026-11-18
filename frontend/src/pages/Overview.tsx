import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, ChevronRight, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorNote, PageHeader, PathConfidenceBadge } from "@/components/common";
import { useCases, useFeedback, useInsights, useMeta, useProcesses } from "@/lib/api";
import { PROCESS_LABEL, caseHref, fmtHours, hoursBetween, median, pct, reviewCounts, reviewedSteps } from "@/lib/utils";

function Tile({ label, value, sub, accent }: { label: string; value?: number; sub?: string; accent?: boolean }) {
  return (
    <Card className="h-full p-5">
      <div className="text-sm text-zinc-600">{label}</div>
      <div className={`mt-2 text-stat tabular-nums tracking-tight ${accent ? "text-indigo-600" : "text-zinc-900"}`}>
        {value === undefined ? <Skeleton className="h-8 w-20" /> : value.toLocaleString("en-GB")}
      </div>
      {sub && <div className="mt-1 text-sm text-zinc-600">{sub}</div>}
    </Card>
  );
}

export default function Overview() {
  const meta = useMeta();
  const procs = useProcesses();
  const cases = useCases();
  const ins = useInsights();
  const fb = useFeedback();
  const reviewed = reviewedSteps(fb.data?.items);
  const all = reviewCounts(cases.data, reviewed);
  const sc = meta.data?.stage_counts;
  const findings = [
    ...(ins.data?.filter((i) => i.kind === "process_insight") ?? []),
    ...(ins.data?.filter((i) => i.kind === "case_flag" && i.rules.includes("activity_after_last_day")) ?? []),
  ];
  const nameOf = (id: string) => cases.data?.find((c) => c.case_id === id)?.subject_name;

  if (meta.error) return <ErrorNote error={meta.error} />;
  return (
    <>
      <PageHeader title="Overview" subtitle="Leave, offboarding and onboarding, rebuilt from mail, calendar, Teams and screen activity, 2–29 March 2026." />

      <div className="grid grid-cols-3 gap-4 xl:grid-cols-5">
        {[
          { label: "Raw records", value: sc?.raw, sub: "mail, calendar, Teams, screen frames" },
          { label: "After dedup + sessions", value: sc?.after_dedup_and_sessions, sub: sc ? `${sc.noise.toLocaleString("en-GB")} of these are noise` : undefined },
          { label: "Process events", value: sc?.process, sub: "leave, offboarding, onboarding" },
          { label: "Cases", value: cases.data?.length, sub: sc ? `${sc.case_steps} steps` : undefined },
          { label: "Steps waiting for review", value: cases.data ? all.waiting : undefined, sub: cases.data ? `${all.done} reviewed so far` : undefined, accent: true },
        ].map((t, i, arr) => (
          <div key={t.label} className="relative h-full">
            <Tile {...t} />
            {i < arr.length - 1 && <ChevronRight className="absolute -right-4 top-1/2 z-10 hidden size-4 xl:block -translate-y-1/2 text-zinc-400" />}
          </div>
        ))}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-4 xl:grid-cols-3">
        {(procs.data ?? [null, null, null]).map((p, i) => {
          if (!p) return <Skeleton key={i} className="h-48" />;
          const cs = cases.data?.filter((c) => c.process === p.process) ?? [];
          const done = cs.filter((c) => c.status === "complete");
          const dur = median(done.map((c) => hoursBetween(c.start, c.last_activity)));
          const rc = reviewCounts(cases.data, reviewed, p.process);
          return (
            <Link key={p.process} to={`/processes/${p.process}`} className="group">
              <Card className="h-full transition-colors group-hover:border-zinc-300">
                <CardHeader className="flex-wrap gap-2">
                  <CardTitle>{p.label}</CardTitle>
                  <PathConfidenceBadge level={p.path_confidence.level} />
                </CardHeader>
                <CardContent>
                  <dl className="grid grid-cols-3 gap-4 text-sm">
                    <div className="flex flex-col"><dt className="text-zinc-600">Cases</dt><dd className="mt-auto whitespace-nowrap pt-1 text-section tabular-nums">{p.case_count}</dd></div>
                    <div className="flex flex-col"><dt className="text-zinc-600">Complete</dt><dd className="mt-auto whitespace-nowrap pt-1 text-section tabular-nums">{pct(p.status_counts.complete ?? 0, p.case_count)}%</dd></div>
                    <div className="flex flex-col"><dt className="text-zinc-600">Median duration</dt><dd className="mt-auto whitespace-nowrap pt-1 text-section tabular-nums">{fmtHours(dur)}</dd></div>
                  </dl>
                  <div className="mt-4">
                    <div className="mb-2 flex justify-between text-sm text-zinc-600"><span>Validated steps</span><span className="tabular-nums">{rc.done} / {rc.total}</span></div>
                    <div className="h-1.5 rounded-full bg-zinc-100"><div className="h-1.5 rounded-full bg-indigo-600" style={{ width: `${pct(rc.done, rc.total)}%` }} /></div>
                  </div>
                  <div className="mt-4 flex items-center gap-1 text-sm text-zinc-600 group-hover:text-indigo-600">Open process map <ArrowRight className="size-4" /></div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader><CardTitle>Top findings</CardTitle><Link to="/insights" className="text-sm text-indigo-600 hover:underline">All insights</Link></CardHeader>
          <CardContent className="p-0 pt-4">
            {!ins.data && <div className="p-5"><Skeleton className="h-40" /></div>}
            {findings.map((f) => {
              const isPattern = f.kind === "process_insight";
              const Icon = f.severity === "warning" ? AlertTriangle : Info;
              const href = isPattern ? `/insights#${encodeURIComponent(f.id)}` : caseHref(f.affected_case_ids[0]);
              return (
                <Link key={f.id} to={href} className="flex gap-3 border-t border-zinc-100 px-5 py-4 last:rounded-b-lg hover:bg-zinc-50">
                  <Icon className={`mt-1 size-4 shrink-0 ${f.severity === "warning" ? "text-amber-600" : "text-zinc-600"}`} />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2 text-base font-medium text-zinc-900">
                      {isPattern ? f.title : `${nameOf(f.affected_case_ids[0]) ?? ""}: ${f.title.toLowerCase()}`}
                      <span className="text-sm font-normal text-zinc-600">{isPattern ? `Pattern · ${PROCESS_LABEL[f.process ?? ""]} · ${f.affected_case_ids.length} cases` : "Case"}</span>
                    </div>
                    <p className="mt-1 text-sm text-zinc-600">{isPattern ? f.message.split(" Systemic because")[0] : (() => { const t = f.message.replace(/^[^:]+:\s*/, ""); return t.charAt(0).toUpperCase() + t.slice(1); })()}</p>
                  </div>
                </Link>
              );
            })}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Seen, not modelled</CardTitle></CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-zinc-600">In the data, but out of scope for this prototype. Kept and labelled, never deleted.</p>
            <ul className="space-y-2 text-sm">
              {meta.data?.seen_not_modelled.map((s) => (
                <li key={s.key} className="flex justify-between gap-4">
                  <span className="min-w-0 text-zinc-700">{s.label}</span>
                  <span className="shrink-0 tabular-nums text-zinc-600">{s.events} msgs{s.screen_sessions ? ` · ${s.screen_sessions} screens` : ""}</span>
                </li>
              )) ?? <Skeleton className="h-24" />}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
