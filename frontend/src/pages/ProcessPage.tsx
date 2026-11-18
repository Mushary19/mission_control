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

const BOX_MIN = 168; // px: narrowest a step box may get before the map wraps to another row
const ARROW = 88; // px: gap between boxes in a row, holds the arrow and the median time

/** Width of an element, kept up to date (0 until the first measurement). */
function useWidth(ref: React.RefObject<HTMLElement>): number {
  const [w, setW] = React.useState(0);
  React.useLayoutEffect(() => {
    if (!ref.current) return;
    setW(ref.current.getBoundingClientRect().width);
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

function Arrow({ hours }: { hours: number | null | undefined }) {
  return (
    <div className="flex shrink-0 flex-col items-center justify-center px-2" style={{ width: ARROW }}>
      <span className="mb-1 text-sm tabular-nums text-zinc-600">{fmtHours(hours)}</span>
      <div className="flex w-full items-center" aria-hidden>
        <div className="h-px flex-1 bg-zinc-400" />
        <svg width="7" height="10" viewBox="0 0 7 10" className="-ml-px shrink-0"><path d="M0 1l6 4-6 4" fill="none" stroke="#a1a1aa" strokeWidth="1.25" /></svg>
      </div>
      <span className="mt-1 text-sm text-zinc-600">median</span>
    </div>
  );
}

/** Return arrow from the last box of one row to the first box of the next (rows read left to right). */
function RowConnector({ from, to, hours }: { from: number; to: number; hours: number | null | undefined }) {
  return (
    <div className="relative h-14" aria-hidden>
      <svg className="absolute inset-0 h-full w-full overflow-visible">
        <path d={`M${from} 0 V24 H${to} V50`} fill="none" stroke="#a1a1aa" strokeWidth="1.25" />
        <path d={`M${to - 4} 45 l4 6 4-6`} fill="none" stroke="#a1a1aa" strokeWidth="1.25" />
      </svg>
      <span className="absolute top-[24px] -translate-x-1/2 -translate-y-1/2 bg-white px-2 text-sm tabular-nums text-zinc-600" style={{ left: (from + to) / 2 }}>
        {fmtHours(hours)} median
      </span>
    </div>
  );
}

function ProcessMap({ model, onPick }: { model: ProcessDetail; onPick: (s: ProcessStep) => void }) {
  const by = Object.fromEntries(model.steps.map((s) => [s.activity, s]));
  const path = model.main_path.activities.map((a) => by[a]).filter(Boolean);
  const optional = model.steps.filter((s) => !s.on_main_path);
  const ref = React.useRef<HTMLDivElement>(null);
  const width = useWidth(ref);
  // As many boxes per row as fit at BOX_MIN, then rows balanced (8 steps -> 4 + 4, not 6 + 2). Never scrolls sideways.
  const fit = width ? Math.max(1, Math.floor((width + ARROW) / (BOX_MIN + ARROW))) : path.length;
  const per = Math.ceil(path.length / Math.ceil(path.length / Math.min(fit, path.length || 1)));
  const boxW = width ? (width - (per - 1) * ARROW) / per : 160;
  const rows: ProcessStep[][] = [];
  for (let i = 0; i < path.length; i += per) rows.push(path.slice(i, i + per));
  const center = (k: number) => k * (boxW + ARROW) + boxW / 2;
  return (
    <div>
      <div ref={ref} className="w-full">
        {rows.map((row, r) => (
          <React.Fragment key={r}>
            <ol className="flex items-stretch" start={r * per + 1}>
              {row.map((s, k) => {
                const i = r * per + k;
                return (
                  <li key={s.activity} className="flex items-stretch">
                    <button
                      onClick={() => onPick(s)}
                      style={{ width: boxW }}
                      className="flex shrink-0 flex-col items-center justify-center rounded-lg border border-zinc-300 bg-white px-4 py-4 text-center hover:border-indigo-600"
                    >
                      <span className="text-sm tabular-nums text-zinc-600">{i + 1}</span>
                      <span className="mt-1 text-base font-medium text-zinc-900">{s.label}</span>
                      <span className="mt-1 text-sm tabular-nums text-zinc-600">{Math.round(s.support_pct)}% of cases</span>
                      <div className="mt-2 w-full"><ConfMix mix={s.confidence_mix} /></div>
                    </button>
                    {k < row.length - 1 && <Arrow hours={s.median_to_next_h} />}
                  </li>
                );
              })}
            </ol>
            {r < rows.length - 1 && <RowConnector from={center(row.length - 1)} to={center(0)} hours={row[row.length - 1].median_to_next_h} />}
          </React.Fragment>
        ))}
      </div>
      {optional.length > 0 && (
        <div className="mt-6">
          <div className="mb-2 text-sm text-zinc-600">Optional or less common steps (under 50% of cases, or off the main path)</div>
          <div className="flex flex-wrap gap-2">
            {optional.map((s) => (
              <button key={s.activity} onClick={() => onPick(s)} className="inline-flex h-8 items-center gap-1 rounded-md border border-dashed border-zinc-300 px-3 text-sm text-zinc-600 hover:border-indigo-600 hover:text-indigo-600">
                {s.label} <span className="tabular-nums text-zinc-600">{Math.round(s.support_pct)}%</span>{s.screen_only && <span className="text-zinc-600">· screen</span>}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="mt-6 flex flex-wrap items-center gap-4 text-sm text-zinc-600">
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
        <div className="space-y-6">
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div><dt className="text-zinc-600">Median from case start</dt><dd className="mt-1 text-base font-medium">{fmtHours(step.median_from_case_start_h)}</dd></div>
            <div><dt className="text-zinc-600">Median to next step</dt><dd className="mt-1 text-base font-medium">{fmtHours(step.median_to_next_h)}</dd></div>
            <div className="col-span-2"><dt className="mb-2 text-zinc-600">Confidence of the evidence</dt><dd><ConfMix mix={step.confidence_mix} /></dd></div>
          </dl>
          <section>
            <h4 className="mb-2 text-card text-zinc-900">Is this step right?</h4>
            <FeedbackButtons base={{ target: "process_step", process: model.process, activity: step.activity }} existing={existing} withComment size="sm" />
          </section>
          <section>
            <h4 className="mb-2 text-card text-zinc-900">Example evidence</h4>
            {qs.some((q) => q.isLoading) && examples.length < 3 && <Loading rows={3} />}
            <ul className="space-y-2">
              {examples.map(({ c, s }) => (
                <li key={s!.event_id} className="rounded-lg border border-zinc-200 p-4">
                  <div className="flex items-center gap-2">
                    <SourceIcon source={s!.source} />
                    <Link to={caseHref(c.case_id)} className="text-sm font-medium text-indigo-600 hover:underline">{c.subject_name}</Link>
                    <span className="ml-auto"><ConfidenceBadge confidence={s!.confidence} likely={s!.likely} /></span>
                  </div>
                  <div className="mt-1 text-sm text-zinc-600">{fmtTime(s!.time_local)} · {s!.actor_name}</div>
                  <p className="mt-2 text-sm text-zinc-700">{s!.title && s!.source !== "teams_chat" ? s!.title : s!.text}</p>
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

      <div className="mb-6 flex flex-wrap items-baseline gap-x-8 gap-y-2 text-sm text-zinc-600">
        <span><strong className="font-semibold text-zinc-900 tabular-nums">{m.case_count}</strong> cases</span>
        {Object.entries(m.status_counts).map(([k, v]) => <span key={k}>{STATUS_LABEL[k]} <strong className="font-semibold tabular-nums text-zinc-900">{v}</strong></span>)}
        <span>Started before 2 Mar <strong className="font-semibold tabular-nums text-zinc-900">{m.window_badges.started_before_window}</strong></span>
        <span>Continues after 29 Mar <strong className="font-semibold tabular-nums text-zinc-900">{m.window_badges.ends_after_window}</strong></span>
        <span className="ml-auto">Validated steps <strong className="font-semibold tabular-nums text-zinc-900">{rc.done} / {rc.total}</strong></span>
      </div>

      <Card>
        <CardHeader><CardTitle>Process map</CardTitle><span className="text-sm text-zinc-600">Click a step for evidence and to confirm or reject it</span></CardHeader>
        <CardContent>
          <ProcessMap model={m} onPick={setPick} />
          <p className="mt-4 text-sm text-zinc-600">How the path was found: {m.main_path.method}.</p>
        </CardContent>
      </Card>

      <div className="mt-8 grid grid-cols-1 gap-8 xl:grid-cols-5 xl:gap-6">
        <section className="xl:col-span-3">
          <h2 className="mb-4 text-section">Variants</h2>
          <Card className="divide-y divide-zinc-100">
            {m.variants.slice(0, allVariants ? undefined : 6).map((v, i) => (
              <div key={i}>
                <button onClick={() => setOpen(open === i ? null : i)} className="flex w-full items-start gap-3 px-5 py-4 text-left hover:bg-zinc-50" aria-expanded={open === i}>
                  {open === i ? <ChevronDown className="mt-1 size-4 shrink-0 text-zinc-600" /> : <ChevronRight className="mt-1 size-4 shrink-0 text-zinc-600" />}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1 text-sm text-zinc-700">
                      {v.path.map((a, j) => (
                        <React.Fragment key={j}>{j > 0 && <span className="text-zinc-500" aria-hidden>→</span>}<span className="whitespace-nowrap rounded-md border border-zinc-300 bg-zinc-50 px-2 py-0.5">{label[a] ?? a}</span></React.Fragment>
                      ))}
                    </div>
                    <div className="mt-2 flex gap-3">{Object.entries(v.statuses).map(([k, n]) => <span key={k} className="text-sm text-zinc-600">{STATUS_LABEL[k]} {n}</span>)}</div>
                  </div>
                  <span className="w-8 shrink-0 text-right text-base font-semibold tabular-nums">{v.count}</span>
                </button>
                {open === i && (
                  <div className="flex flex-wrap gap-2 pb-4 pl-12 pr-5">
                    {v.case_ids.map((id) => <Link key={id} to={caseHref(id)} className="rounded-md border border-zinc-300 px-2 py-0.5 text-sm hover:border-indigo-600 hover:text-indigo-600">{name(id)}</Link>)}
                  </div>
                )}
              </div>
            ))}
          </Card>
          {m.variants.length > 6 && <Button variant="link" size="xs" className="mt-2" onClick={() => setAllVariants((x) => !x)}>{allVariants ? "Show fewer" : `Show all ${m.variants.length} variants`}</Button>}
          <p className="mt-2 text-sm text-zinc-600">Variants use explicit steps only (screen steps are left out); repeats are collapsed.</p>
        </section>
        <section className="xl:col-span-2">
          <h2 className="mb-4 text-section">Open questions for staff</h2>
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-1">{m.open_questions.map((oq) => <QuestionCard key={oq.id} q={oq} feedback={fb.data?.items} />)}</div>
        </section>
      </div>

      <section className="mt-8">
        <h2 className="mb-4 text-section">Insights</h2>
        {m.insights.length === 0 ? <Empty>No insights for this process.</Empty> : (
          <div className="space-y-4">{m.insights.map((i) => <InsightCard key={i.id} insight={i} cases={cases.data} feedback={fb.data?.items} />)}</div>
        )}
      </section>

      <StepPanel model={m} step={pick} onClose={() => setPick(null)} />
      <AddStep model={m} open={adding} onClose={() => setAdding(false)} />
    </>
  );
}
