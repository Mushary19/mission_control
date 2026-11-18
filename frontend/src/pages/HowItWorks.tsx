import { ArrowRight, FileJson } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceBadge, ErrorNote, Loading, PageHeader } from "@/components/common";
import { useMeta } from "@/lib/api";

const n = (x?: number) => (x ?? 0).toLocaleString("en-GB");

export default function HowItWorks() {
  const meta = useMeta();
  if (meta.error) return <ErrorNote error={meta.error} />;
  if (!meta.data) return <Loading rows={6} />;
  const s = meta.data.stage_counts;
  const steps = [
    { n: 1, title: "Ingest", file: "1_events.jsonl", count: s.raw, unit: "raw records", note: `Mail, calendar, Teams, ${n(s.screen_frames)} screen frames. Times to Sri Lanka time + UTC. Duplicates across mailboxes merged.` },
    { n: 2, title: "Clean", file: "2_events_clean.jsonl", count: s.after_dedup_and_sessions, unit: "events after dedup + screen sessions", note: `Text rules label each record: ${n(s.process)} process, ${n(s.context)} context, ${n(s.noise)} noise, ${n(s.out_of_scope)} out of scope. Names resolved to people.` },
    { n: 3, title: "Cases", file: "3_cases.json", count: s.cases, unit: "cases", note: `${n(s.case_steps)} steps. Leave by person + dates; offboarding and onboarding by person. Nameless screens joined by time only.` },
    { n: 4, title: "Discover", file: "4_processes.json", count: 3, unit: "process models", note: "Step support, directly-follows graph, variants, main path, median times. The order comes from the data, not from a template." },
    { n: 5, title: "Flags", file: "5_flags.json", count: s.flags, unit: "flags", note: "Rule checks: activity after the last day, laptop late, open day-one issue, cancel with no follow-up, sick leave two ways." },
    { n: 6, title: "Insights", file: "6_insights.json", count: undefined, unit: "patterns vs case flags", note: "A rule that hits at least 3 cases and half of the eligible ones is a pattern; the rest stay case flags." },
  ];
  return (
    <>
      <PageHeader title="How it works" subtitle="From raw exports to the screens you are reviewing. Everything runs on this machine; no data is sent anywhere." />
      <div className="grid grid-cols-3 gap-4 xl:grid-cols-6">
        {steps.map((st, i) => (
          <div key={st.n} className="relative h-full">
            <Card className="flex h-full flex-col p-5">
              <div className="text-xs text-zinc-500">Step {st.n}</div>
              <div className="text-card text-zinc-900">{st.title}</div>
              <div className="mt-2 text-stat tabular-nums">{st.count === undefined ? "—" : n(st.count)}</div>
              <div className="text-xs text-zinc-500">{st.unit}</div>
              <p className="mt-2 text-xs text-zinc-600">{st.note}</p>
              <a href={`/api/files/${st.file}`} target="_blank" rel="noreferrer" className="mt-auto flex items-center gap-1 pt-4 font-mono text-micro text-indigo-600 hover:underline"><FileJson className="size-4 shrink-0" />out/{st.file}</a>
            </Card>
            {i < steps.length - 1 && <ArrowRight className="absolute -right-4 top-1/2 z-10 hidden size-4 -translate-y-1/2 text-zinc-300 xl:block" />}
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-zinc-500">
        All output files (committed under <span className="font-mono">out/</span>, opened read-only):{" "}
        {meta.data.out_files.map((f, i) => (
          <span key={f}>{i > 0 && ", "}<a href={`/api/files/${f}`} target="_blank" rel="noreferrer" className="font-mono text-indigo-600 hover:underline">{f}</a></span>
        ))}
      </p>

      <div className="mt-8 grid grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>Rules, in short</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm text-zinc-700">
            <p><strong className="font-medium">Activities</strong> come from fixed text rules (the messages are templated), e.g. “Is that ok on your side?” = Client asked; “Got …'s laptop back, wiped” = Laptop received.</p>
            <p><strong className="font-medium">Screen windows</strong> are read by title and address only (the app name is unreliable). Frames of the same window within 10 minutes form one session.</p>
            <p><strong className="font-medium">Names</strong> are matched in this order: email address, full name, first name + initial, first name or typo with case context. When more than one person still fits, the record stays “ambiguous”.</p>
            <p><strong className="font-medium">Noise</strong> (small talk, newsletters, news sites, lock screen) and out-of-scope work (recruitment, birthdays, laptop replacements, payroll) are kept with a reason, never deleted.</p>
            <p><strong className="font-medium">No AI model is used.</strong> In production, an LLM could read free-text mail, new templates and hard name matches, with staff confirming the result here.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Honesty rules</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm text-zinc-700">
            <p><strong className="font-medium">{meta.data.coverage.label}</strong> Not exported: {meta.data.coverage.not_exported.map((x) => `${x.name} (${x.job_title})`).join(", ")}. Steps that happen only in their mailboxes are missing.</p>
            <p className="flex flex-wrap items-center gap-2">Every step shows its evidence strength: <ConfidenceBadge confidence="high" /> explicit message, <ConfidenceBadge confidence="medium" /> calendar or name matched by context, <ConfidenceBadge confidence="low" likely /> seen on screen or linked by time.</p>
            <p><strong className="font-medium">A screen shows what was open, not what was done.</strong> Screen steps are always “Likely”.</p>
            <p><strong className="font-medium">Window badges.</strong> The export covers 2–29 March. “Started before 2 Mar” and “Continues after 29 Mar” mean steps are outside the data, not missing.</p>
            <p><strong className="font-medium">Every step links to its raw record</strong> (“Proof”), read from the export unchanged.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
