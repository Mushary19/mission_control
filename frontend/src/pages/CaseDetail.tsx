import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, ArrowRightLeft, ChevronDown, ChevronRight, Lightbulb, Plus, UserRoundSearch } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { ConfidenceBadge, ErrorNote, FeedbackButtons, Loading, PageHeader, Proof, SourceIcon, StatusBadge, TimeNote, WindowBadges } from "@/components/common";
import type { CaseDetail as Case, CaseStep } from "@/lib/api";
import { useCase, useFeedback, useInsights, usePerson, usePostFeedback, useProcess } from "@/lib/api";
import { useReviewer } from "@/lib/reviewer";
import { PROCESS_LABEL, RULE_LABEL, SOURCE_LABEL, caseHref, fmtDay, fmtTime } from "@/lib/utils";

const TRIVIAL = new Set(["email", "sender", "chat_member", "full_name", "unresolved"]);
const sentence = (m: string) => { const t = m.replace(/^[^:]+:\s*/, ""); return t.charAt(0).toUpperCase() + t.slice(1); };

function StepRow({ c, s, existing }: { c: Case; s: CaseStep; existing: ReturnType<typeof useFeedback>["data"] }) {
  const [open, setOpen] = React.useState(false);
  const mine = existing?.items.filter((f) => f.target === "case_step" && f.case_id === c.case_id && f.event_id === s.event_id);
  const who = s.resolution && !TRIVIAL.has(s.resolution.method) ? s.resolution.reason : null;
  const body = s.source === "screen" ? s.title : s.source === "mail" || s.source === "calendar" ? s.title : s.text;
  return (
    <li className="relative pl-9">
      <span className="absolute left-0 top-0"><SourceIcon source={s.source} /></span>
      <div className="rounded-lg border border-zinc-200">
        <div className="flex items-start gap-3 px-3 py-2.5">
          <button onClick={() => setOpen((o) => !o)} className="flex min-w-0 flex-1 items-start gap-2 text-left" aria-expanded={open}>
            {open ? <ChevronDown className="mt-0.5 size-4 shrink-0 text-zinc-400" /> : <ChevronRight className="mt-0.5 size-4 shrink-0 text-zinc-400" />}
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-[13px] font-medium text-zinc-900">{s.label}</span>
                <ConfidenceBadge confidence={s.confidence} likely={s.likely} />
                <span className="text-xs text-zinc-500">{s.actor_name}</span>
              </div>
              {body && <p className="mt-0.5 line-clamp-1 text-xs text-zinc-600">{body}</p>}
              <p className="mt-0.5 text-xs text-zinc-400">
                {who && <>{who}. </>}{s.link === "thread" || s.link === "dates" || s.link === "person" ? null : s.link_reason}
                {s.session && <> Screen session: {s.session.frame_count} frame{s.session.frame_count > 1 ? "s" : ""}, {Math.round(s.session.minutes)} min.</>}
              </p>
            </div>
          </button>
          <span className="shrink-0 whitespace-nowrap pt-0.5 text-xs tabular-nums text-zinc-500">{fmtTime(s.time_local)}</span>
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-zinc-100 px-3 py-2">
          <FeedbackButtons base={{ target: "case_step", case_id: c.case_id, event_id: s.event_id, activity: s.activity, process: c.process }} existing={mine} withComment />
          {!open && <Button variant="link" size="xs" onClick={() => setOpen(true)}>Proof</Button>}
        </div>
        {open && (
          <div className="space-y-2 border-t border-zinc-100 bg-zinc-50/50 px-3 py-3">
            <div className="text-xs text-zinc-500">
              <span className="font-medium text-zinc-700">Proof</span> · {SOURCE_LABEL[s.source]} · joined this case: {s.link_reason}
            </div>
            {s.text && s.source !== "screen" && <p className="whitespace-pre-line rounded-lg border border-zinc-200 bg-white px-3 py-2 text-[13px] text-zinc-800">{s.text}</p>}
            <Proof eventId={s.event_id} />
          </div>
        )}
      </div>
    </li>
  );
}

function SamePerson({ personId }: { personId: string }) {
  const p = usePerson(personId);
  const fb = useFeedback();
  const other = p.data?.possible_same_person[0];
  const o = usePerson(other?.person_id);
  if (!other) return null;
  const existing = fb.data?.items.filter((f) => f.target === "identity" && f.person_id === personId && f.other_person_id === other.person_id);
  return (
    <Card className="mb-4 border-amber-200 bg-amber-50/40">
      <div className="flex items-start gap-3 px-4 py-3">
        <UserRoundSearch className="mt-0.5 size-4 shrink-0 text-amber-700" />
        <div className="flex-1">
          <div className="text-[13px] font-medium">Is this the same person?</div>
          <p className="mt-0.5 text-xs text-zinc-600">
            Two records are called {p.data?.display_name}: {p.data?.emails.join(", ")} and {o.data?.emails.join(", ") || "another record"}. They were kept apart because the {other.reason}.
          </p>
          <div className="mt-2">
            <FeedbackButtons base={{ target: "identity", person_id: personId, other_person_id: other.person_id }} existing={existing} />
          </div>
          <p className="mt-1 text-[11px] text-zinc-400">Confirm = same person · Reject = different people</p>
        </div>
      </div>
    </Card>
  );
}

function AddCaseStep({ c }: { c: Case }) {
  const proc = useProcess(c.process);
  const { user } = useReviewer();
  const post = usePostFeedback();
  const [activity, setActivity] = React.useState("");
  const [day, setDay] = React.useState("");
  const [note, setNote] = React.useState("");
  const save = () =>
    post.mutate({ user, target: "case_step", verdict: "add", case_id: c.case_id, process: c.process, activity: activity || null, note, proposed_step: { activity: activity || "other", date: day || null } }, {
      onSuccess: () => { toast.success("Saved"); setActivity(""); setDay(""); setNote(""); },
      onError: (e) => toast.error(e.message),
    });
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-1.5"><Plus className="size-3.5" />Add a missing step</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="as-act">Activity</Label>
            <Select id="as-act" value={activity} onChange={(e) => setActivity(e.target.value)} className="w-full">
              <option value="">Something else</option>
              {proc.data?.steps.map((s) => <option key={s.activity} value={s.activity}>{s.label}</option>)}
            </Select>
          </div>
          <div className="space-y-1"><Label htmlFor="as-date">Date</Label><Input id="as-date" type="date" min="2026-02-01" max="2026-04-30" value={day} onChange={(e) => setDay(e.target.value)} /></div>
        </div>
        <div className="space-y-1"><Label htmlFor="as-note">Note</Label><Textarea id="as-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="What happened, and where is it recorded?" /></div>
        <Button size="sm" onClick={save} disabled={(!activity && !note.trim()) || post.isPending}>Save step</Button>
      </CardContent>
    </Card>
  );
}

export default function CaseDetail() {
  const { caseId } = useParams();
  const q = useCase(caseId);
  const fb = useFeedback();
  const ins = useInsights();
  const proc = useProcess(q.data?.process);
  const lab = (a: string) => proc.data?.steps.find((x) => x.activity === a)?.label ?? a.replace(/_/g, " ");
  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <Loading rows={10} />;
  const c = q.data;
  const patterns = ins.data?.filter((i) => c.insights.includes(i.id)) ?? [];
  const inPattern = new Set(patterns.flatMap((p) => p.per_case.flatMap((x) => x.flag_ids)));
  const ownFlags = c.flags.filter((f) => !inPattern.has(f.flag_id));
  const staff = new Set(c.staff_involved.map((s) => s.name));
  let lastOwner: string | null = null;
  const caseFeedback = fb.data?.items.filter((f) => f.case_id === c.case_id && f.target === "case_step" && f.verdict === "add") ?? [];
  const key = c.key as { dates?: { raw: string }; last_day?: string; first_day?: string; leave_type?: string };

  return (
    <>
      <Link to="/cases" className="mb-3 inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-900"><ArrowLeft className="size-3" />Cases</Link>
      <PageHeader
        title={c.subject_name}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>{PROCESS_LABEL[c.process]}{key.leave_type ? ` · ${key.leave_type} leave` : ""}{key.dates ? ` · ${key.dates.raw}` : ""}{key.last_day ? ` · last day ${fmtDay(key.last_day)}` : ""}{key.first_day ? ` · first day ${fmtDay(key.first_day)}` : ""}</span>
            {c.client_name && <span>Client: {c.client_name}</span>}
            <span>Owner: {c.owner_name ?? "—"}</span>
            <span>{fmtDay(c.start)} – {fmtDay(c.last_activity)}</span>
          </span>
        }
        right={<span className="flex items-center gap-2"><WindowBadges before={c.started_before_window} after={c.ends_after_window} notes={c.window_notes} /><StatusBadge status={c.status} /></span>}
      />

      <SamePerson personId={c.subject_person_id} />

      {(ownFlags.length > 0 || c.related_flags.length > 0 || patterns.length > 0) && (
        <Card className="mb-5">
          <CardHeader><CardTitle>Flags</CardTitle></CardHeader>
          <CardContent className="space-y-2 pt-2">
            {ownFlags.map((f) => (
              <div key={f.flag_id} className="flex gap-2 text-[13px]"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" /><div><span className="font-medium">{RULE_LABEL[f.rule] ?? f.rule}. </span><span className="text-zinc-700">{sentence(f.message)}</span></div></div>
            ))}
            {c.related_flags.map((f) => (
              <div key={f.flag_id} className="flex gap-2 text-[13px]">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
                <div><span className="font-medium">On another case: {RULE_LABEL[f.rule] ?? f.rule}. </span><span className="text-zinc-700">{sentence(f.message)} </span>{f.case_id && <Link to={caseHref(f.case_id)} className="text-indigo-600 hover:underline">Open {PROCESS_LABEL[f.process ?? ""]?.toLowerCase()} case</Link>}</div>
              </div>
            ))}
            {patterns.map((p) => (
              <div key={p.id} className="flex gap-2 text-[13px]"><Lightbulb className="mt-0.5 size-4 shrink-0 text-zinc-400" /><div><span className="font-medium">Part of a pattern: </span><Link to={`/insights#${encodeURIComponent(p.id)}`} className="text-indigo-600 hover:underline">{p.title}</Link><span className="text-zinc-600"> — {sentence(p.per_case.find((x) => x.case_id === c.case_id)?.message ?? "")}</span></div></div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-3 gap-6">
        <section className="col-span-2">
          <h2 className="mb-3 text-[13px] font-semibold">Timeline <span className="font-normal text-zinc-400">· {c.steps.length} steps</span></h2>
          <ol className="relative space-y-2 before:absolute before:bottom-2 before:left-3 before:top-2 before:w-px before:bg-zinc-200">
            {c.steps.map((s) => {
              const isOwner = s.actor_name && staff.has(s.actor_name);
              const marker = isOwner && lastOwner && lastOwner !== s.actor_name ? `${lastOwner} → ${s.actor_name}` : null;
              if (isOwner) lastOwner = s.actor_name!;
              return (
                <React.Fragment key={s.event_id}>
                  {marker && (
                    <li className="relative flex items-center gap-2 pl-9 text-xs font-medium text-indigo-700">
                      <span className="absolute left-0 flex size-6 items-center justify-center rounded-md border border-indigo-200 bg-indigo-50"><ArrowRightLeft className="size-3.5" /></span>
                      Handoff: {marker}
                    </li>
                  )}
                  <StepRow c={c} s={s} existing={fb.data} />
                </React.Fragment>
              );
            })}
          </ol>
          <TimeNote />
          {c.out_of_order.length > 0 && (
            <p className="mt-2 text-xs text-zinc-500">Order note: {c.out_of_order.map((o) => `${lab(o.later)} came after ${lab(o.earlier).toLowerCase()}`).join("; ")}.</p>
          )}
        </section>
        <aside className="space-y-4">
          <AddCaseStep c={c} />
          {caseFeedback.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Steps added by staff</CardTitle></CardHeader>
              <CardContent className="space-y-2 pt-2 text-[13px]">
                {caseFeedback.map((f) => (
                  <div key={f.id} className="rounded-lg bg-zinc-50 px-3 py-2">
                    <div className="flex items-center gap-2"><Badge variant="accent">Added</Badge><span className="font-medium">{f.activity ? lab(f.activity) : "Other step"}</span>{(f.proposed_step as { date?: string })?.date && <span className="text-xs text-zinc-500">{fmtDay((f.proposed_step as { date: string }).date)}</span>}</div>
                    {f.note && <p className="mt-1 text-zinc-700">{f.note}</p>}
                    <div className="mt-1 text-xs text-zinc-400">{f.user}</div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader><CardTitle>Summary</CardTitle></CardHeader>
            <CardContent className="pt-2 text-[13px] text-zinc-600">{c.summary}</CardContent>
          </Card>
        </aside>
      </div>
    </>
  );
}
