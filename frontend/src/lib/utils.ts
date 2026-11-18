import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { CaseSummary, Feedback, ProcessDetail } from "./api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-03-09T08:36:00+05:30" -> "Mon 9 Mar, 08:36". Reads the local wall-clock from the string (Sri Lanka time), never the browser zone. */
export function fmtTime(iso?: string | null, withTime = true): string {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
  if (!m) return iso;
  const [, y, mo, d, h, mi] = m;
  const wd = WD[new Date(Date.UTC(+y, +mo - 1, +d)).getUTCDay()];
  const day = `${wd} ${+d} ${MO[+mo - 1]}`;
  return withTime && h ? `${day}, ${h}:${mi}` : day;
}
export const fmtDay = (iso?: string | null) => fmtTime(iso, false);

export function fmtHours(h: number | null | undefined): string {
  if (h === null || h === undefined) return "—";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${h < 10 ? h.toFixed(1).replace(/\.0$/, "") : Math.round(h)} h`;
  return `${(h / 24).toFixed(1).replace(/\.0$/, "")} d`;
}

export const pct = (n: number, d: number) => (d ? Math.round((100 * n) / d) : 0);

export function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export const hoursBetween = (a: string, b: string) => (new Date(b).getTime() - new Date(a).getTime()) / 3_600_000;

export const STATUS_LABEL: Record<string, string> = { complete: "Complete", in_progress: "In progress", declined: "Declined", cancelled: "Cancelled" };
export const PROCESS_LABEL: Record<string, string> = { leave: "Leave", offboarding: "Offboarding", onboarding: "Onboarding" };
export const SOURCE_LABEL: Record<string, string> = { mail: "Mail", calendar: "Calendar", teams_chat: "Teams chat", teams_channel: "Teams channel", screen: "Screen" };
export const RULE_LABEL: Record<string, string> = {
  activity_after_last_day: "Activity after the last day",
  cancel_no_followup: "Cancel request with no follow-up",
  onboarded_before_laptop: "Onboarded before the laptop arrived",
  laptop_requested_late: "Laptop requested late",
  onboarded_with_open_issue: "Onboarded with an open day-one issue",
  sick_leave_two_ways: "Sick leave handled two ways",
};

/** activity id -> human label, from every process model (labels come from the rule table via the API). */
export function labelMap(models: (ProcessDetail | undefined)[]): Record<string, string> {
  const m: Record<string, string> = {};
  for (const p of models) for (const s of p?.steps ?? []) m[s.activity] = s.label;
  return m;
}
export const humanize = (id: string, labels: Record<string, string>) =>
  labels[id] ?? id.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/** Steps reviewed = distinct (case, event) pairs with case_step confirm/reject feedback. */
export function reviewedSteps(items: Feedback[] | undefined): Set<string> {
  const s = new Set<string>();
  for (const f of items ?? []) if (f.target === "case_step" && f.event_id && (f.verdict === "confirm" || f.verdict === "reject")) s.add(`${f.case_id}|${f.event_id}`);
  return s;
}
export function reviewCounts(cases: CaseSummary[] | undefined, reviewed: Set<string>, process?: string) {
  const cs = (cases ?? []).filter((c) => !process || c.process === process);
  const total = cs.reduce((n, c) => n + c.step_count, 0);
  const ids = new Set(cs.map((c) => c.case_id));
  let done = 0;
  for (const k of reviewed) if (ids.has(k.split("|")[0])) done++;
  return { total, done, waiting: Math.max(0, total - done) };
}

export function storageGet(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
export function storageSet(key: string, v: string) {
  try { window.localStorage.setItem(key, v); } catch { /* private mode: keep in memory only */ }
}

export const caseHref = (id: string) => `/cases/${encodeURIComponent(id)}`;
