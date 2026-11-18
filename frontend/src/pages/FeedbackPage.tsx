import { Link } from "react-router-dom";
import { Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Empty, ErrorNote, Loading, PageHeader, TimeNote } from "@/components/common";
import { toLocal } from "@/components/Cards";
import type { Feedback } from "@/lib/api";
import { useAllProcesses, useCases, useFeedback, useInsights } from "@/lib/api";
import { PROCESS_LABEL, caseHref, fmtTime, humanize, labelMap } from "@/lib/utils";

const TARGET: Record<string, string> = { process_step: "Process step", case_step: "Case step", case: "Case", open_question: "Question", insight: "Insight", identity: "Same person?" };
const VERDICT: Record<string, { label: string; v: "green" | "red" | "accent" | "muted" }> = {
  confirm: { label: "Confirm", v: "green" }, reject: { label: "Reject", v: "red" }, add: { label: "Add", v: "accent" }, answer: { label: "Answer", v: "muted" },
};

export default function FeedbackPage() {
  const fb = useFeedback();
  const cases = useCases();
  const ins = useInsights();
  const procs = useAllProcesses();
  const labels = labelMap(procs.map((p) => p.data));
  const qs = Object.fromEntries(procs.flatMap((p) => p.data?.open_questions ?? []).map((q) => [q.id, q.question]));
  const caseName = (id?: string | null) => cases.data?.find((c) => c.case_id === id)?.subject_name;
  const what = (f: Feedback) => {
    switch (f.target) {
      case "case_step":
      case "case":
        return <><Link to={caseHref(f.case_id!)} className="text-indigo-600 hover:underline">{caseName(f.case_id) ?? "Case"}</Link>{f.activity && <> · {humanize(f.activity, labels)}</>}</>;
      case "process_step":
        return <><Link to={`/processes/${f.process}`} className="text-indigo-600 hover:underline">{PROCESS_LABEL[f.process ?? ""]}</Link> · {f.activity ? humanize(f.activity, labels) : String((f.proposed_step as { name?: string })?.name ?? "New step")}</>;
      case "open_question":
        return <Link to="/questions" className="text-indigo-600 hover:underline">{qs[f.question_id!] ?? "Question"}</Link>;
      case "insight":
        return <Link to={`/insights#${encodeURIComponent(f.insight_id!)}`} className="text-indigo-600 hover:underline">{ins.data?.find((i) => i.id === f.insight_id)?.title ?? "Insight"}</Link>;
      case "identity":
        return <>Two records for one person</>;
    }
  };
  return (
    <>
      <PageHeader
        title="Feedback"
        subtitle="Everything staff confirmed, rejected, added or answered. Saved on this machine (SQLite + out/feedback.jsonl)."
        right={<Button variant="outline" asChild><a href="/api/feedback/export" download="feedback.jsonl"><Download />Export JSONL</a></Button>}
      />
      {fb.error ? <ErrorNote error={fb.error} /> : !fb.data ? <Loading rows={6} /> : fb.data.items.length === 0 ? (
        <Empty>No feedback yet. Open a case and confirm or reject a step.</Empty>
      ) : (
        <Card>
          <Table>
            <THead><TR><TH>When</TH><TH>Who</TH><TH>Target</TH><TH>About</TH><TH>Verdict</TH><TH>Note</TH></TR></THead>
            <TBody>
              {[...fb.data.items].reverse().map((f) => (
                <TR key={f.id}>
                  <TD className="whitespace-nowrap tabular-nums text-zinc-500">{fmtTime(toLocal(f.created_at))}</TD>
                  <TD className="whitespace-nowrap">{f.user}</TD>
                  <TD className="whitespace-nowrap text-zinc-600">{TARGET[f.target]}</TD>
                  <TD className="min-w-[200px]">{what(f)}</TD>
                  <TD><Badge variant={VERDICT[f.verdict].v}>{VERDICT[f.verdict].label}</Badge></TD>
                  <TD className="min-w-[200px] max-w-[320px] text-zinc-600">{f.note || <span className="text-zinc-300">—</span>}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}
      <TimeNote />
    </>
  );
}
