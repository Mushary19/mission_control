import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import { Tip } from "@/components/ui/tooltip";
import { ConfidenceBadge, Empty, ErrorNote, FeedbackButtons, Loading, PageHeader, PathConfidenceBadge, Proof, SourceIcon } from "@/components/common";
import { InsightCard, QuestionCard } from "@/components/Cards";
import type { ProcessDetail, ProcessStep } from "@/lib/api";
import { useCaseList, useCases, useFeedback, usePostFeedback, useProcess } from "@/lib/api";
import { useReviewer } from "@/lib/reviewer";
import { STATUS_LABEL, caseHref, fmtHours, fmtTime, reviewCounts, reviewedSteps } from "@/lib/utils";

function ConfMix({ mix }: { mix: Record<string, number> }) {
  const total = (mix.high ?? 0) + (mix.medium ?? 0) + (mix.low ?? 0) || 1;
  const seg = (k: string, cls: string) => (mix[k] ? <div className={cls} style={{ width: `${(100 * mix[k]) / total}%` }} /> : null);
  return (
    <Tip content={`High ${mix.high ?? 0} · Medium ${mix.medium ?? 0} · Likely ${mix.low ?? 0}`}>
      <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-zinc-100" aria-label="Confidence mix">
        {seg("high", "bg-zinc-900")}{seg("medium", "bg-zinc-400")}{seg("low", "bg-[repeating-linear-gradient(90deg,#a1a1aa_0_2px,transparent_2px_4px)]")}
      </div>
    </Tip>
  );
}

function ProcessMap({ model, onPick }: { model: ProcessDetail; onPick: (s: ProcessStep) => void }) {
  const by = Object.fromEntries(model.steps.map((s) => [s.activity, s]));
  const path = model.main_path.activities.map((a) => by[a]).filter(Boolean);
  const optional = model.steps.filter((s) => !s.on_main_path);
  return (
    <div>
      <div className="overflow-x-auto pb-2">
        <ol className="flex min-w-max items-stretch">
          {path.map((s, i) => (
            <li key={s.activity} className="flex items-stretch">
              <button
                onClick={() => onPick(s)}
                className="flex w-[150px] flex-col rounded-lg border border-zinc-200 bg-white px-3 py-2.5 text-left hover:border-indigo-600"
              >
                <span className="text-[11px] tabular-nums text-zinc-400">{i + 1}</span>
                <span className="mt-0.5 line-clamp-2 min-h-[36px] text-[13px] font-medium leading-snug text-zinc-900">{s.label}</span>
                <span className="mt-1 text-xs tabular-nums text-zinc-500">{Math.round(s.support_pct)}% of cases</span>
                <div className="mt-2"><ConfMix mix={s.confidence_mix} /></div>
              </button>
              {i < path.length - 1 && (
                <div className="flex w-[64px] flex-col items-center justify-center">
                  <span className="mb-1 text-[11px] tabular-nums text-zinc-500">{fmtHours(s.median_to_next_h)}</span>
                  <svg width="56" height="10" viewBox="0 0 56 10" aria-hidden><path d="M0 5h50" stroke="#a1a1aa" strokeWidth="1" /><path d="M48 1l6 4-6 4" fill="none" stroke="#a1a1aa" strokeWidth="1" /></svg>
                  <span className="mt-1 text-[10px] text-zinc-400">median</span>
                </div>
              )}
            </li>
          ))}
        </ol>
      </div>
      {optional.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-xs text-zinc-500">Optional or less common steps (under 50% of cases, or off the main path)</div>
          <div className="flex flex-wrap gap-1.5">
            {optional.map((s) => (
              <button key={s.activity} onClick={() => onPick(s)} className="rounded-md border border-dashed border-zinc-300 px-2 py-1 text-xs text-zinc-600 hover:border-indigo-600 hover:text-indigo-600">
                {s.label} <span className="tabular-nums text-zinc-400">{Math.round(s.support_pct)}%</span>{s.screen_only && <span className="ml-1 text-zinc-400">· screen</span>}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="mt-4 flex items-center gap-4 text-[11px] text-zinc-500">
        <span className="flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full bg-zinc-900" />High</span>
        <span className="flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full bg-zinc-400" />Medium</span>
        <span className="flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full bg-[repeating-linear-gradient(90deg,#a1a1aa_0_2px,transparent_2px_4px)]" />Likely</span>
        <span>Times on arrows: median between steps</span>
      </div>
    </div>
  );
}

function StepPanel({ model, step, onClose }: { model: ProcessDetail; step: ProcessStep | null; onClose: () => void }) {
  const ids = React.useMemo(() => {
    if (!step) return [];
    const out: string[] = [];
    for (const v of model.variants) for (const id of v.case_ids) if (!out.includes(id)) out.push(id);
    return out;
  }, [model, step]);
  const qs = useCaseList(step ? ids : []);
  const fb = useFeedback();
  const [proof, setProof] = React.useState<string | null>(null);
  const examples = qs
    .map((q) => q.data)
    .filter(Boolean)
    .map((c) => ({ c: c!, s: c!.steps.find((x) => x.activity === step?.activity) }))
    .filter((x) => x.s)
    .slice(0, 3);
  const existing = fb.data?.items.filter((f) => f.target === "process_step" && f.process === model.process && f.activity === step?.activity);
  return (
    <Sheet open={!!step} onOpenChange={(o) => !o && onClose()} title={step?.label ?? ""} description={step ? `${Math.round(step.support_pct)}% of ${model.label.toLowerCase()} cases (${step.case_count})` : ""}>
      {step && (
        <div className="space-y-5">
          <dl className="grid grid-cols-2 gap-3 text-xs">
            <div><dt className="text-zinc-500">Median from case start</dt><dd className="mt-0.5 text-[13px] font-medium">{fmtHours(step.median_from_case_start_h)}</dd></div>
            <div><dt className="text-zinc-500">Median to next step</dt><dd className="mt-0.5 text-[13px] font-medium">{fmtHours(step.median_to_next_h)}</dd></div>
            <div className="col-span-2"><dt className="mb-1 text-zinc-500">Confidence of the evidence</dt><dd><ConfMix mix={step.confidence_mix} /></dd></div>
          </dl>
          <section>
            <h4 className="mb-2 text-xs font-medium text-zinc-600">Is this step right?</h4>
            <FeedbackButtons base={{ target: "process_step", process: model.process, activity: step.activity }} existing={existing} withComment size="sm" />
          </section>
          <section>
            <h4 className="mb-2 text-xs font-medium text-zinc-600">Example evidence</h4>
            {qs.some((q) => q.isLoading) && examples.length < 3 && <Loading rows={3} />}
            <ul className="space-y-2">
              {examples.map(({ c, s }) => (
                <li key={s!.event_id} className="rounded-lg border border-zinc-200 p-3">
                  <div className="flex items-center gap-2">
                    <SourceIcon source={s!.source} />
                    <Link to={caseHref(c.case_id)} className="text-[13px] font-medium text-indigo-600 hover:underline">{c.subject_name}</Link>
                    <span className="ml-auto"><ConfidenceBadge confidence={s!.confidence} likely={s!.likely} /></span>
                  </div>
                  <div className="mt-1 text-xs text-zinc-500">{fmtTime(s!.time_local)} · {s!.actor_name}</div>
                  <p className="mt-1.5 line-clamp-3 text-[13px] text-zinc-700">{s!.title && s!.source !== "teams_chat" ? s!.title : s!.text}</p>
                  <Button variant="link" size="xs" className="mt-1" onClick={() => setProof(proof === s!.event_id ? null : s!.event_id)}>{proof === s!.event_id ? "Hide proof" : "Show proof"}</Button>
                  {proof === s!.event_id && <div className="mt-2"><Proof eventId={s!.event_id} /></div>}
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </Sheet>
  );
}

function AddStep({ model, open, onClose }: { model: ProcessDetail; open: boolean; onClose: () => void }) {
  const { user } = useReviewer();
  const post = usePostFeedback();
  const [name, setName] = React.useState("");
  const [after, setAfter] = React.useState(model.main_path.activities[0] ?? "");
  const [note, setNote] = React.useState("");
  const save = () =>
    post.mutate({ user, target: "process_step", verdict: "add", process: model.process, note, proposed_step: { name, after } }, {
      onSuccess: () => { toast.success("Saved"); setName(""); setNote(""); onClose(); },
      onError: (e) => toast.error(e.message),
    });
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()} title="Add a missing step" description={`Something you do in ${model.label.toLowerCase()} that the data does not show.`}>
      <div className="space-y-3">
        <div className="space-y-1"><Label htmlFor="ms-name">What is the step?</Label><Input id="ms-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Ask the client for DMS access" /></div>
        <div className="space-y-1">
          <Label htmlFor="ms-after">It happens after</Label>
          <Select id="ms-after" value={after} onChange={(e) => setAfter(e.target.value)} className="w-full">
            {model.steps.map((s) => <option key={s.activity} value={s.activity}>{s.label}</option>)}
          </Select>
        </div>
        <div className="space-y-1"><Label htmlFor="ms-note">Note</Label><Textarea id="ms-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Who does it, and where is it recorded?" /></div>
        <Button onClick={save} disabled={!name.trim() || post.isPending}>Save step</Button>
      </div>
    </Sheet>
  );
}

export default function ProcessPage() {
  const { process } = useParams();
  const q = useProcess(process);
  const cases = useCases();
  const fb = useFeedback();
  const [pick, setPick] = React.useState<ProcessStep | null>(null);
  const [adding, setAdding] = React.useState(false);
  const [open, setOpen] = React.useState<number | null>(null);
  const [allVariants, setAllVariants] = React.useState(false);
  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <Loading rows={8} />;
  const m = q.data;
  const label = Object.fromEntries(m.steps.map((s) => [s.activity, s.label]));
  const rc = reviewCounts(cases.data, reviewedSteps(fb.data?.items), m.process);
  const name = (id: string) => cases.data?.find((c) => c.case_id === id)?.subject_name ?? "Case";
  return (
    <>
      <PageHeader
        title={m.label}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <PathConfidenceBadge level={m.path_confidence.level} />
            <span>Based on {m.full_trace_cases} complete case{m.full_trace_cases === 1 ? "" : "s"} inside the window — {m.path_confidence.level} confidence. {(() => { const r = m.path_confidence.reason.split("; ").slice(1).join("; "); return r.charAt(0).toUpperCase() + r.slice(1); })()}</span>
          </span>
        }
        right={<Button variant="outline" onClick={() => setAdding(true)}><Plus />Add a missing step</Button>}
      />

      <div className="mb-4 flex flex-wrap gap-4 text-xs text-zinc-500">
        <span><strong className="font-semibold text-zinc-900 tabular-nums">{m.case_count}</strong> cases</span>
        {Object.entries(m.status_counts).map(([k, v]) => <span key={k}>{STATUS_LABEL[k]} <strong className="font-semibold tabular-nums text-zinc-900">{v}</strong></span>)}
        <span>Started before 2 Mar <strong className="font-semibold tabular-nums text-zinc-900">{m.window_badges.started_before_window}</strong></span>
        <span>Continues after 29 Mar <strong className="font-semibold tabular-nums text-zinc-900">{m.window_badges.ends_after_window}</strong></span>
        <span className="ml-auto">Validated steps <strong className="font-semibold tabular-nums text-zinc-900">{rc.done} / {rc.total}</strong></span>
      </div>

      <Card>
        <CardHeader><CardTitle>Process map</CardTitle><span className="text-xs text-zinc-400">Click a step for evidence and to confirm or reject it</span></CardHeader>
        <CardContent>
          <ProcessMap model={m} onPick={setPick} />
          <p className="mt-3 text-xs text-zinc-400">How the path was found: {m.main_path.method}.</p>
        </CardContent>
      </Card>

      <div className="mt-6 grid grid-cols-5 gap-6">
        <section className="col-span-3">
          <h2 className="mb-2 text-[13px] font-semibold">Variants</h2>
          <Card className="divide-y divide-zinc-100">
            {m.variants.slice(0, allVariants ? undefined : 6).map((v, i) => (
              <div key={i}>
                <button onClick={() => setOpen(open === i ? null : i)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-zinc-50" aria-expanded={open === i}>
                  {open === i ? <ChevronDown className="mt-0.5 size-4 shrink-0 text-zinc-400" /> : <ChevronRight className="mt-0.5 size-4 shrink-0 text-zinc-400" />}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1 text-xs text-zinc-700">
                      {v.path.map((a, j) => (
                        <React.Fragment key={j}>{j > 0 && <span className="text-zinc-300">→</span>}<span className="rounded bg-zinc-100 px-1.5 py-0.5">{label[a] ?? a}</span></React.Fragment>
                      ))}
                    </div>
                    <div className="mt-1.5 flex gap-1">{Object.entries(v.statuses).map(([k, n]) => <span key={k} className="text-[11px] text-zinc-500">{STATUS_LABEL[k]} {n}</span>)}</div>
                  </div>
                  <span className="text-[13px] font-semibold tabular-nums">{v.count}</span>
                </button>
                {open === i && (
                  <div className="flex flex-wrap gap-1.5 px-11 pb-3">
                    {v.case_ids.map((id) => <Link key={id} to={caseHref(id)} className="rounded-md border border-zinc-200 px-2 py-0.5 text-xs hover:border-indigo-600 hover:text-indigo-600">{name(id)}</Link>)}
                  </div>
                )}
              </div>
            ))}
          </Card>
          {m.variants.length > 6 && <Button variant="link" size="xs" className="mt-2" onClick={() => setAllVariants((x) => !x)}>{allVariants ? "Show fewer" : `Show all ${m.variants.length} variants`}</Button>}
          <p className="mt-2 text-xs text-zinc-400">Variants use explicit steps only (screen steps are left out); repeats are collapsed.</p>
        </section>
        <section className="col-span-2 space-y-3">
          <h2 className="text-[13px] font-semibold">Open questions for staff</h2>
          {m.open_questions.map((oq) => <QuestionCard key={oq.id} q={oq} feedback={fb.data?.items} />)}
        </section>
      </div>

      <section className="mt-6">
        <h2 className="mb-2 text-[13px] font-semibold">Insights</h2>
        {m.insights.length === 0 ? <Empty>No insights for this process.</Empty> : (
          <div className="space-y-3">{m.insights.map((i) => <InsightCard key={i.id} insight={i} cases={cases.data} feedback={fb.data?.items} />)}</div>
        )}
      </section>

      <StepPanel model={m} step={pick} onClose={() => setPick(null)} />
      <AddStep model={m} open={adding} onClose={() => setAdding(false)} />
    </>
  );
}
