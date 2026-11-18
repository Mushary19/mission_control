import { useLocation } from "react-router-dom";
import { Empty, ErrorNote, Loading, PageHeader } from "@/components/common";
import { InsightCard } from "@/components/Cards";
import { useCases, useFeedback, useInsights } from "@/lib/api";

export default function Insights() {
  const ins = useInsights();
  const cases = useCases();
  const fb = useFeedback();
  const focus = decodeURIComponent(useLocation().hash.slice(1));
  if (ins.error) return <ErrorNote error={ins.error} />;
  if (!ins.data) return <Loading rows={6} />;
  const patterns = ins.data.filter((i) => i.kind === "process_insight");
  const flags = ins.data.filter((i) => i.kind === "case_flag");
  const groups = flags.reduce<Record<string, typeof flags>>((m, f) => ((m[f.title] ??= []).push(f), m), {});
  return (
    <>
      <PageHeader title="Insights" subtitle="Patterns repeat across many cases and point at the process. Case flags are one-off and point at a single case." />
      <h2 className="mb-4 text-section">Process patterns <span className="text-base font-normal text-zinc-500">· {patterns.length}</span></h2>
      <div className="space-y-4">{patterns.map((i) => <InsightCard key={i.id} insight={i} cases={cases.data} feedback={fb.data?.items} highlight={focus === i.id} />)}</div>
      <h2 className="mb-4 mt-8 text-section">Case flags <span className="text-base font-normal text-zinc-500">· {flags.length}</span></h2>
      {flags.length === 0 ? <Empty>No case flags.</Empty> : Object.entries(groups).map(([title, fs]) => (
        <section key={title} className="mb-6">
          <h3 className="mb-2 text-card text-zinc-600">{title} · {fs.length}</h3>
          <div className="space-y-2">{fs.map((i) => <InsightCard key={i.id} insight={i} cases={cases.data} feedback={fb.data?.items} highlight={focus === i.id} />)}</div>
        </section>
      ))}
    </>
  );
}
