import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Flag, Search } from "lucide-react";
import { Input, Select } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Card } from "@/components/ui/card";
import { Empty, ErrorNote, Loading, PageHeader, StatusBadge, TimeNote, WindowBadges } from "@/components/common";
import { useCases, useInsights } from "@/lib/api";
import { PROCESS_LABEL, STATUS_LABEL, caseHref, fmtTime } from "@/lib/utils";

export default function Cases() {
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const cases = useCases();
  const ins = useInsights();
  const process = sp.get("process") ?? "";
  const status = sp.get("status") ?? "";
  const flagged = sp.get("flagged") ?? "";
  const q = sp.get("q") ?? "";
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v); else n.delete(k);
    setSp(n, { replace: true });
  };
  const inPattern = new Set(ins.data?.filter((i) => i.kind === "process_insight").flatMap((i) => i.affected_case_ids) ?? []);
  const rows = (cases.data ?? []).filter((c) => {
    if (process && c.process !== process) return false;
    if (status && c.status !== status) return false;
    const isFlagged = c.flag_count > 0 || inPattern.has(c.case_id);
    if (flagged === "yes" && !isFlagged) return false;
    if (flagged === "no" && isFlagged) return false;
    if (q && !`${c.subject_name} ${c.client_name ?? ""} ${c.owner_name ?? ""} ${c.summary}`.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });
  return (
    <>
      <PageHeader title="Cases" subtitle="One row per leave request, offboarding or onboarding. Newest activity first." />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="pointer-events-none absolute left-3 top-2 size-4 text-zinc-400" />
          <Input value={q} onChange={(e) => set("q", e.target.value)} placeholder="Search person, client, owner" className="pl-9" aria-label="Search" />
        </div>
        <Select value={process} onChange={(e) => set("process", e.target.value)} aria-label="Process">
          <option value="">All processes</option>
          {Object.entries(PROCESS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select value={status} onChange={(e) => set("status", e.target.value)} aria-label="Status">
          <option value="">All statuses</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select value={flagged} onChange={(e) => set("flagged", e.target.value)} aria-label="Flags">
          <option value="">Flagged or not</option>
          <option value="yes">Flagged</option>
          <option value="no">Not flagged</option>
        </Select>
        <span className="ml-auto text-xs tabular-nums text-zinc-500">{rows.length} of {cases.data?.length ?? 0}</span>
      </div>
      {cases.error ? <ErrorNote error={cases.error} /> : !cases.data ? <Loading rows={10} /> : rows.length === 0 ? (
        <Empty>No cases match these filters. Clear the search or pick “All processes”.</Empty>
      ) : (
        <Card>
          <Table>
            <THead>
              <TR><TH>Person</TH><TH>Process</TH><TH>Client</TH><TH>Owner</TH><TH>Status</TH><TH>Window</TH><TH className="text-right">Steps</TH><TH className="text-right">Flags</TH><TH>Last activity</TH></TR>
            </THead>
            <TBody>
              {rows.map((c) => {
                const flags = c.flag_count + (inPattern.has(c.case_id) ? 1 : 0);
                return (
                  <TR key={c.case_id} className="cursor-pointer hover:bg-zinc-50" onClick={() => nav(caseHref(c.case_id))}>
                    <TD className="whitespace-nowrap"><Link to={caseHref(c.case_id)} className="font-medium text-zinc-900 hover:text-indigo-600" onClick={(e) => e.stopPropagation()}>{c.subject_name}</Link></TD>
                    <TD className="text-zinc-600">{PROCESS_LABEL[c.process]}</TD>
                    <TD className="whitespace-nowrap text-zinc-600">{c.client_name ?? "—"}</TD>
                    <TD className="whitespace-nowrap text-zinc-600">{c.owner_name ?? "—"}</TD>
                    <TD><StatusBadge status={c.status} /></TD>
                    <TD><WindowBadges before={c.started_before_window} after={c.ends_after_window} /></TD>
                    <TD className="text-right tabular-nums">{c.step_count}</TD>
                    <TD className="text-right tabular-nums">{flags ? <span className="inline-flex items-center gap-1 text-amber-700"><Flag className="size-4" />{flags}</span> : <span className="text-zinc-400">0</span>}</TD>
                    <TD className="whitespace-nowrap tabular-nums text-zinc-500">{fmtTime(c.last_activity)}</TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        </Card>
      )}
      <TimeNote />
    </>
  );
}
