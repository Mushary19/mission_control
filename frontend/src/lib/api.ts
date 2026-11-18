// Types mirror backend/schemas.py. The UI reads only the /api endpoints.
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

export type Process = "leave" | "offboarding" | "onboarding";
export type Status = "complete" | "in_progress" | "declined" | "cancelled";
export type Confidence = "high" | "medium" | "low";
export type Source = "mail" | "calendar" | "teams_chat" | "teams_channel" | "screen";

export interface StaffRef { name: string; job_title: string; folder?: string | null }
export interface SeenNotModelled { key: string; label: string; events: number; screen_sessions: number }
export interface Meta {
  coverage: { staff_total: number; staff_exported: number; label: string; exported: StaffRef[]; not_exported: StaffRef[] };
  window: { start: string; end: string; timezone: string; note?: string };
  timezone_note: string;
  stage_counts: Record<string, number>;
  seen_not_modelled: SeenNotModelled[];
  out_files: string[];
}
export interface PathConfidence { level: Confidence; reason: string; rule: string }
export interface ProcessSummary {
  process: Process; label: string; case_count: number; status_counts: Record<string, number>;
  window_badges: Record<string, number>; full_trace_cases: number; path_confidence: PathConfidence;
  main_path_labels: string[]; open_question_count: number; insight_count: number;
}
export interface ProcessStep {
  activity: string; label: string; support_pct: number; case_count: number; confidence_mix: Record<string, number>;
  on_main_path: boolean; optional: boolean; median_from_case_start_h: number | null; median_to_next_h: number | null;
  next_on_main_path: string | null; screen_only: boolean;
}
export interface Variant { path: string[]; count: number; case_ids: string[]; statuses: Record<string, number> }
export interface OpenQuestion { id: string; process: Process; question: string; why: string; evidence: Record<string, unknown> }
export interface InsightCase { case_id: string; person_name?: string | null; rules: string[]; message: string; flag_ids: string[] }
export interface Insight {
  id: string; kind: "process_insight" | "case_flag"; process: Process | null; title: string; message: string; rules: string[];
  affected_case_ids: string[]; evidence_event_ids: string[]; severity: "info" | "warning"; per_case: InsightCase[]; eligible_cases?: number | null;
}
export interface ProcessDetail extends ProcessSummary {
  main_path: { activities: string[]; labels: string[]; method: string; cases_following_exactly: number; tied_alternatives: { path: string[]; count: number }[] };
  steps: ProcessStep[]; dfg: { from: string; to: string; count: number }[]; variants: Variant[];
  open_questions: OpenQuestion[]; insights: Insight[];
}
export interface CaseSummary {
  case_id: string; process: Process; subject_person_id: string; subject_name: string; client?: string | null; client_name?: string | null;
  owner_staff_id?: string | null; owner_name?: string | null; status: Status; started_before_window: boolean; ends_after_window: boolean;
  step_count: number; flag_count: number; start: string; last_activity: string; summary: string;
}
export interface Resolution { method: string; confidence: Confidence | null; reason?: string | null; raw_name?: string | null; candidates: string[] }
export interface Session { start_local: string; end_local: string; frame_count: number; minutes: number }
export interface CaseStep {
  activity: string; label: string; event_id: string; time_local: string; actor_id?: string | null; actor_name?: string | null; source: Source;
  confidence: Confidence; likely: boolean; link: string; link_reason: string; raw_ref: { file: string; line: number };
  session?: Session | null; title?: string | null; text?: string | null; resolution?: Resolution | null;
}
export interface Flag {
  flag_id: string; rule: string; scope: "case" | "process"; severity: string; case_id?: string | null; process?: Process | null;
  person_id?: string | null; person_name?: string | null; message: string; evidence_event_ids: string[];
}
export interface CaseDetail extends CaseSummary {
  key: Record<string, unknown>; staff_involved: { person_id: string | null; name: string | null }[]; handoff: boolean; window_notes: string[];
  steps: CaseStep[]; flags: Flag[]; related_flags: Flag[]; insights: string[]; out_of_order: Record<string, string>[];
}
export interface PersonDetail {
  person_id: string; display_name: string; emails: string[]; kind: string; org_name?: string | null;
  possible_same_person: { person_id: string; name?: string | null; reason: string }[]; cases: CaseSummary[];
}
export interface RawResponse { event_id: string; source: Source; line_count: number; lines: { file: string; line: number; raw: string; record: unknown }[] }
export type Target = "process_step" | "case_step" | "case" | "open_question" | "insight" | "identity";
export type Verdict = "confirm" | "reject" | "add" | "answer";
export interface FeedbackIn {
  user: string; target: Target; verdict: Verdict; process?: Process | null; case_id?: string | null; activity?: string | null;
  event_id?: string | null; question_id?: string | null; insight_id?: string | null; person_id?: string | null; other_person_id?: string | null;
  note?: string; proposed_step?: Record<string, unknown> | null;
}
export interface Feedback extends FeedbackIn { id: string; created_at: string }

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json() as Promise<T>;
}

export const enc = (s: string) => encodeURIComponent(s);
export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: () => get<Meta>("/api/meta"), staleTime: Infinity });
export const useProcesses = () => useQuery({ queryKey: ["processes"], queryFn: () => get<ProcessSummary[]>("/api/processes"), staleTime: Infinity });
export const useProcess = (p: string | undefined) =>
  useQuery({ queryKey: ["process", p], queryFn: () => get<ProcessDetail>(`/api/processes/${p}`), enabled: !!p, staleTime: Infinity });
export const useAllProcesses = () =>
  useQueries({ queries: (["leave", "offboarding", "onboarding"] as const).map((p) => ({ queryKey: ["process", p], queryFn: () => get<ProcessDetail>(`/api/processes/${p}`), staleTime: Infinity })) });
export const useCases = () => useQuery({ queryKey: ["cases"], queryFn: () => get<CaseSummary[]>("/api/cases"), staleTime: Infinity });
export const useCase = (id: string | undefined) =>
  useQuery({ queryKey: ["case", id], queryFn: () => get<CaseDetail>(`/api/cases/${enc(id!)}`), enabled: !!id, staleTime: Infinity });
export const useCaseList = (ids: string[]) =>
  useQueries({ queries: ids.map((id) => ({ queryKey: ["case", id], queryFn: () => get<CaseDetail>(`/api/cases/${enc(id)}`), staleTime: Infinity })) });
export const useInsights = () => useQuery({ queryKey: ["insights"], queryFn: () => get<Insight[]>("/api/insights"), staleTime: Infinity });
export const usePerson = (id: string | undefined) =>
  useQuery({ queryKey: ["person", id], queryFn: () => get<PersonDetail>(`/api/people/${enc(id!)}`), enabled: !!id, staleTime: Infinity });
export const useRaw = (eventId: string, enabled: boolean) =>
  useQuery({ queryKey: ["raw", eventId], queryFn: () => get<RawResponse>(`/api/events/${eventId.split("/").map(enc).join("/")}/raw`), enabled, staleTime: Infinity });
export const useFeedback = () =>
  useQuery({ queryKey: ["feedback"], queryFn: () => get<{ count: number; items: Feedback[] }>("/api/feedback"), staleTime: 5_000 });

export function usePostFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: FeedbackIn) => {
      const r = await fetch("/api/feedback", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
      return j as Feedback;
    },
    onSuccess: (fb) => {
      qc.setQueryData<{ count: number; items: Feedback[] }>(["feedback"], (old) => (old ? { count: old.count + 1, items: [...old.items, fb] } : old));
      qc.invalidateQueries({ queryKey: ["feedback"] });
    },
  });
}
