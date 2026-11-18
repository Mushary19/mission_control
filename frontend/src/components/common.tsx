import * as React from "react";
import { Calendar, Check, Hash, Mail, MessageSquare, Monitor, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Tip } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import type { Confidence, Feedback, FeedbackIn, Source, Status } from "@/lib/api";
import { usePostFeedback, useRaw } from "@/lib/api";
import { SOURCE_LABEL, STATUS_LABEL, cn, fmtTime } from "@/lib/utils";
import { useReviewer } from "@/lib/reviewer";

/** One rule everywhere: High = solid dark, Medium = outline, Likely (low / screen) = dashed + "Likely". */
export function ConfidenceBadge({ confidence, likely }: { confidence: Confidence; likely?: boolean }) {
  if (likely || confidence === "low")
    return <Tip content="Seen on screen or linked by time only. Shows what was open, not what was done."><Badge variant="dashed">Likely</Badge></Tip>;
  if (confidence === "high") return <Tip content="An explicit message names the action and the person, or it is in the same thread."><Badge variant="solid">High</Badge></Tip>;
  return <Tip content="A calendar entry, or the person was matched by a short name, typo or case context."><Badge variant="outline">Medium</Badge></Tip>;
}

const SOURCE_ICON: Record<Source, React.ComponentType<{ className?: string }>> = { mail: Mail, calendar: Calendar, teams_chat: MessageSquare, teams_channel: Hash, screen: Monitor };
export function SourceIcon({ source, className }: { source: Source; className?: string }) {
  const I = SOURCE_ICON[source];
  return (
    <Tip content={SOURCE_LABEL[source]}>
      <span className={cn("inline-flex size-6 shrink-0 items-center justify-center rounded-md border border-zinc-200 bg-white text-zinc-500", className)} aria-label={SOURCE_LABEL[source]}>
        <I className="size-3.5" />
      </span>
    </Tip>
  );
}

export function StatusBadge({ status }: { status: Status }) {
  const v = status === "complete" ? "green" : status === "in_progress" ? "outline" : "muted";
  return <Badge variant={v as "green" | "outline" | "muted"}>{STATUS_LABEL[status]}</Badge>;
}

export function WindowBadges({ before, after, notes }: { before: boolean; after: boolean; notes?: string[] }) {
  if (!before && !after) return null;
  const tip = notes?.length ? notes.map((n) => n[0].toUpperCase() + n.slice(1)).join(". ") + "." : undefined;
  return (
    <span className="inline-flex gap-1">
      {before && <Tip content={tip ?? "The case started before 2 Mar: earlier steps are not in the data."}><Badge variant="dashed">Started before 2 Mar</Badge></Tip>}
      {after && <Tip content={tip ?? "The case continues after 29 Mar: later steps are not in the data."}><Badge variant="dashed">Continues after 29 Mar</Badge></Tip>}
    </span>
  );
}

export function PathConfidenceBadge({ level }: { level: Confidence }) {
  const map = { high: "solid", medium: "outline", low: "dashed" } as const;
  return <Badge variant={map[level]}>{level[0].toUpperCase() + level.slice(1)} confidence</Badge>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-dashed border-zinc-200 px-4 py-6 text-center text-[13px] text-zinc-500">{children}</div>;
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  return <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">Could not load: {String((error as Error)?.message ?? error)}. Is the API running on port 8000?</div>;
}

export function PageHeader({ title, subtitle, right }: { title: React.ReactNode; subtitle?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-[20px] font-semibold tracking-tight text-zinc-900">{title}</h1>
        {subtitle && <div className="mt-1 text-[13px] text-zinc-500">{subtitle}</div>}
      </div>
      {right}
    </div>
  );
}

export function TimeNote() {
  return <p className="mt-3 text-xs text-zinc-400">All times in Sri Lanka time (UTC+05:30)</p>;
}

/** Confirm / Reject (+ optional comment) for any feedback target. Shows the latest verdict already given. */
export function FeedbackButtons({ base, existing, withComment = false, size = "xs" }: { base: Omit<FeedbackIn, "user" | "verdict">; existing?: Feedback[]; withComment?: boolean; size?: "xs" | "sm" }) {
  const { user } = useReviewer();
  const post = usePostFeedback();
  const [comment, setComment] = React.useState(false);
  const [note, setNote] = React.useState("");
  const last = [...(existing ?? [])].reverse().find((f) => f.verdict === "confirm" || f.verdict === "reject");
  const send = (verdict: "confirm" | "reject", n = "") =>
    post.mutate({ ...base, user, verdict, note: n }, { onSuccess: () => { toast.success("Saved"); setComment(false); setNote(""); }, onError: (e) => toast.error(String(e.message)) });
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <Button variant={last?.verdict === "confirm" ? "subtle" : "outline"} size={size} onClick={() => send("confirm")} disabled={post.isPending}><ThumbsUp />Confirm</Button>
        <Button variant={last?.verdict === "reject" ? "subtle" : "outline"} size={size} onClick={() => send("reject")} disabled={post.isPending}><ThumbsDown />Reject</Button>
        {withComment && <Button variant="ghost" size={size} onClick={() => setComment((c) => !c)}>Comment</Button>}
        {last && (
          <span className="inline-flex items-center gap-1 text-xs text-zinc-500">
            {last.verdict === "confirm" ? <Check className="size-3.5 text-emerald-600" /> : <X className="size-3.5 text-red-600" />}
            {last.verdict === "confirm" ? "Confirmed" : "Rejected"} by {last.user}
          </span>
        )}
      </div>
      {comment && (
        <div className="space-y-2">
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="What is right or wrong about this step?" />
          <div className="flex gap-1.5">
            <Button size="xs" onClick={() => send("confirm", note)} disabled={!note.trim()}>Confirm with note</Button>
            <Button size="xs" variant="outline" onClick={() => send("reject", note)} disabled={!note.trim()}>Reject with note</Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Proof: the original raw record(s) for an event, exactly as exported. */
export function Proof({ eventId }: { eventId: string }) {
  const q = useRaw(eventId, true);
  const [all, setAll] = React.useState(false);
  if (q.isLoading) return <Skeleton className="h-24 w-full" />;
  if (q.error) {
    const msg = String((q.error as Error).message ?? q.error);
    if (msg.startsWith("503"))
      return <div className="rounded-lg border border-dashed border-zinc-300 px-3 py-3 text-[13px] text-zinc-600">Raw data not available on this server. The export is only deployed with private copies; the step and its file + line reference are still shown above.</div>;
    return <ErrorNote error={q.error} />;
  }
  const lines = q.data!.lines;
  const shown = all ? lines : lines.slice(0, 3);
  return (
    <div className="space-y-2">
      <div className="text-xs text-zinc-500">
        {q.data!.line_count === 1 ? "Raw record" : `${q.data!.line_count} raw screen frames (one session)`} · read from the export, unchanged
      </div>
      {shown.map((l) => (
        <div key={`${l.file}:${l.line}`} className="rounded-lg border border-zinc-200">
          <div className="border-b border-zinc-200 bg-zinc-50 px-3 py-1.5 font-mono text-[11px] text-zinc-600">{l.file} · line {l.line}</div>
          <pre className="max-h-72 overflow-auto px-3 py-2 font-mono text-[11px] leading-relaxed text-zinc-800">{JSON.stringify(l.record, null, 2)}</pre>
        </div>
      ))}
      {lines.length > 3 && !all && <Button variant="link" size="xs" onClick={() => setAll(true)}>Show all {lines.length} frames</Button>}
    </div>
  );
}

export function When({ iso }: { iso: string }) {
  return <span className="tabular-nums text-zinc-500">{fmtTime(iso)}</span>;
}
