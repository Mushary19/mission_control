import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorNote, PageHeader, PathConfidenceBadge } from "@/components/common";
import { useCases, useFeedback, useInsights, useMeta, useProcesses } from "@/lib/api";
import { PROCESS_LABEL, caseHref, fmtHours, hoursBetween, median, pct, reviewCounts, reviewedSteps } from "@/lib/utils";

function Tile({ label, value, sub, accent }: { label: string; value?: number; sub?: string; accent?: boolean }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className={`mt-1 text-[26px] font-semibold tabular-nums tracking-tight ${accent ? "text-indigo-600" : "text-zinc-900"}`}>
        {value === undefined ? <Skeleton className="h-8 w-20" /> : value.toLocaleString("en-GB")}
      </div>
      {sub && <div className="mt-0.5 text-xs text-zinc-400">{sub}</div>}
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

      <div className="grid grid-cols-4 gap-3">
        <Tile label="Raw records" value={sc?.raw} sub="mail, calendar, Teams, screen frames" />
        <Tile label="After cleaning" value={sc ? sc.process : undefined} sub={sc ? `process events, from ${sc.after_dedup_and_sessions.toLocaleString("en-GB")} after dedup + sessions` : undefined} />
        <Tile label="Cases" value={cases.data?.length} sub={sc ? `${sc.case_steps} steps` : undefined} />
        <Tile label="Steps waiting for review" value={cases.data ? all.waiting : undefined} sub={cases.data ? `${all.done} reviewed so far` : undefined} accent />
      </div>

      <div className="mt-6 grid grid-cols-3 gap-3">
        {(procs.data ?? [null, null, null]).map((p, i) => {
          if (!p) return <Skeleton key={i} className="h-44" />;
          const cs = cases.data?.filter((c) => c.process === p.process) ?? [];
          const done = cs.filter((c) => c.status === "complete");
          const dur = median(done.map((c) => hoursBetween(c.start, c.last_activity)));
          const rc = reviewCounts(cases.data, reviewed, p.process);
          return (
            <Link key={p.process} to={`/processes/${p.process}`} className="group">
              <Card className="h-full transition-colors group-hover:border-zinc-300">
                <CardHeader>
                  <CardTitle className="text-[14px]">{p.label}</CardTitle>
                  <PathConfidenceBadge level={p.path_confidence.level} />
                </CardHeader>
                <CardContent>
                  <dl className="grid grid-cols-3 gap-2 text-xs">
                    <div><dt className="text-zinc-500">Cases</dt><dd className="mt-0.5 text-[16px] font-semibold tabular-nums">{p.case_count}</dd></div>
                    <div><dt className="text-zinc-500">Complete</dt><dd className="mt-0.5 text-[16px] font-semibold tabular-nums">{pct(p.status_counts.complete ?? 0, p.case_count)}%</dd></div>
                    <div><dt className="text-zinc-500">Median duration</dt><dd className="mt-0.5 text-[16px] font-semibold tabular-nums">{fmtHours(dur)}</dd></div>
                  </dl>
                  <div className="mt-4">
                    <div className="mb-1 flex justify-between text-xs text-zinc-500"><span>Validated steps</span><span className="tabular-nums">{rc.done} / {rc.total}</span></div>
                    <div className="h-1.5 rounded-full bg-zinc-100"><div className="h-1.5 rounded-full bg-indigo-600" style={{ width: `${pct(rc.done, rc.total)}%` }} /></div>
                  </div>
                  <div className="mt-3 flex items-center gap-1 text-xs text-zinc-400 group-hover:text-indigo-600">Open process map <ArrowRight className="size-3" /></div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <div className="mt-6 grid grid-cols-3 gap-3">
        <Card className="col-span-2">
          <CardHeader><CardTitle>Top findings</CardTitle><Link to="/insights" className="text-xs text-indigo-600 hover:underline">All insights</Link></CardHeader>
          <CardContent className="space-y-0 p-0 pt-2">
            {!ins.data && <div className="p-4"><Skeleton className="h-40" /></div>}
            {findings.map((f) => {
              const isPattern = f.kind === "process_insight";
              const Icon = f.severity === "warning" ? AlertTriangle : Info;
              const href = isPattern ? `/insights#${encodeURIComponent(f.id)}` : caseHref(f.affected_case_ids[0]);
              return (
                <Link key={f.id} to={href} className="flex gap-3 border-t border-zinc-100 px-4 py-3 hover:bg-zinc-50">
                  <Icon className={`mt-0.5 size-4 shrink-0 ${f.severity === "warning" ? "text-amber-600" : "text-zinc-400"}`} />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-900">
                      {isPattern ? f.title : `${nameOf(f.affected_case_ids[0]) ?? ""}: ${f.title.toLowerCase()}`}
                      <span className="text-[11px] font-normal text-zinc-400">{isPattern ? `Pattern · ${PROCESS_LABEL[f.process ?? ""]} · ${f.affected_case_ids.length} cases` : "Case"}</span>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-zinc-500">{isPattern ? f.message.split(" Systemic because")[0] : (() => { const t = f.message.replace(/^[^:]+:\s*/, ""); return t.charAt(0).toUpperCase() + t.slice(1); })()}</p>
                  </div>
                </Link>
              );
            })}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Seen, not modelled</CardTitle></CardHeader>
          <CardContent>
            <p className="mb-3 text-xs text-zinc-500">In the data, but out of scope for this prototype. Kept and labelled, never deleted.</p>
            <ul className="space-y-2 text-[13px]">
              {meta.data?.seen_not_modelled.map((s) => (
                <li key={s.key} className="flex justify-between gap-2">
                  <span className="text-zinc-700">{s.label}</span>
                  <span className="shrink-0 tabular-nums text-zinc-500">{s.events} msgs{s.screen_sessions ? ` · ${s.screen_sessions} screens` : ""}</span>
                </li>
              )) ?? <Skeleton className="h-24" />}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
