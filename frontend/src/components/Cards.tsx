import * as React from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Info } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { FeedbackButtons } from "@/components/common";
import type { CaseSummary, Feedback, Insight, OpenQuestion } from "@/lib/api";
import { usePostFeedback } from "@/lib/api";
import { useReviewer } from "@/lib/reviewer";
import { PROCESS_LABEL, caseHref, fmtTime } from "@/lib/utils";

function patternReason(i: Insight): string {
  const n = i.affected_case_ids.length;
  if (i.rules.includes("sick_leave_two_ways")) return `Process-level rule: it compares all ${i.eligible_cases ?? n} sick-leave cases, not one case.`;
  if (i.message.includes("Systemic because")) return i.message.split("Systemic because ")[1].replace(/\.$/, "") + " — the same issue at several clients points to the process, not one person.";
  return `It hits ${n} of ${i.eligible_cases ?? n} eligible cases (a pattern needs at least 3 cases and at least half of the eligible ones).`;
}

export function InsightCard({ insight, cases, feedback, highlight }: { insight: Insight; cases?: CaseSummary[]; feedback?: Feedback[]; highlight?: boolean }) {
  const name = (id: string) => cases?.find((c) => c.case_id === id)?.subject_name ?? "Case";
  const Icon = insight.severity === "warning" ? AlertTriangle : Info;
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { if (highlight) ref.current?.scrollIntoView({ block: "center" }); }, [highlight]);
  const mine = feedback?.filter((f) => f.target === "insight" && f.insight_id === insight.id);
  return (
    <Card ref={ref} id={insight.id} className={highlight ? "border-indigo-600" : undefined}>
      <div className="flex gap-3 px-4 py-4">
        <Icon className={`mt-0.5 size-4 shrink-0 ${insight.severity === "warning" ? "text-amber-600" : "text-zinc-400"}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[14px] font-semibold">{insight.title}</h3>
            <Badge variant="muted">{PROCESS_LABEL[insight.process ?? ""]}</Badge>
            {insight.kind === "process_insight" && <Badge variant="accent">Pattern</Badge>}
          </div>
          <p className="mt-1 text-[13px] text-zinc-700">{insight.kind === "process_insight" ? insight.message.split(" Systemic because")[0] : insight.message}</p>
          {insight.kind === "process_insight" && (
            <p className="mt-2 text-xs text-zinc-500"><span className="font-medium text-zinc-600">Why this is a pattern: </span>{patternReason(insight)}</p>
          )}
          {insight.per_case.length > 0 ? (
            <ul className="mt-3 divide-y divide-zinc-100 rounded-lg border border-zinc-200">
              {insight.per_case.map((p) => (
                <li key={p.case_id} className="flex items-baseline gap-3 px-3 py-2 text-[13px]">
                  <Link to={caseHref(p.case_id)} className="w-40 shrink-0 font-medium text-indigo-600 hover:underline">{p.person_name ?? name(p.case_id)}</Link>
                  <span className="text-zinc-600">{(() => { const t = p.message.replace(/^[^:]+:\s*/, ""); return t.charAt(0).toUpperCase() + t.slice(1); })()}</span>
                </li>
              ))}
            </ul>
          ) : insight.affected_case_ids.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {insight.affected_case_ids.map((id) => (
                <Link key={id} to={caseHref(id)} className="rounded-md border border-zinc-200 px-2 py-0.5 text-xs text-zinc-700 hover:border-indigo-600 hover:text-indigo-600">{name(id)}</Link>
              ))}
            </div>
          )}
          <div className="mt-3"><FeedbackButtons base={{ target: "insight", insight_id: insight.id, process: insight.process }} existing={mine} withComment /></div>
        </div>
      </div>
    </Card>
  );
}

export function QuestionCard({ q, feedback }: { q: OpenQuestion; feedback?: Feedback[] }) {
  const { user } = useReviewer();
  const post = usePostFeedback();
  const [text, setText] = React.useState("");
  const answers = feedback?.filter((f) => f.target === "open_question" && f.question_id === q.id) ?? [];
  const save = () =>
    post.mutate({ user, target: "open_question", verdict: "answer", process: q.process, question_id: q.id, note: text.trim() }, {
      onSuccess: () => { toast.success("Saved"); setText(""); },
      onError: (e) => toast.error(e.message),
    });
  return (
    <Card className="px-4 py-4">
      <h3 className="text-[14px] font-medium text-zinc-900">{q.question}</h3>
      <p className="mt-1 text-xs text-zinc-500">{q.why}</p>
      {answers.length > 0 && (
        <ul className="mt-3 space-y-2">
          {answers.map((a) => (
            <li key={a.id} className="rounded-lg bg-zinc-50 px-3 py-2 text-[13px]">
              <div className="text-xs text-zinc-500">{a.user} · {fmtTime(toLocal(a.created_at))}</div>
              <div className="mt-0.5 text-zinc-800">{a.note}</div>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex items-end gap-2">
        <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Your answer" className="min-h-[40px]" aria-label={`Answer: ${q.question}`} />
        <Button onClick={save} disabled={!text.trim() || post.isPending}>Save</Button>
      </div>
    </Card>
  );
}

/** UTC timestamp -> Sri Lanka wall clock string (for feedback times). */
export function toLocal(utc: string): string {
  const d = new Date(new Date(utc).getTime() + 5.5 * 3600_000);
  return d.toISOString().replace("Z", "+05:30");
}
